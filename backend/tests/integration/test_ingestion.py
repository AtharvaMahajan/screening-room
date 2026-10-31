"""Ingestion end to end against a FakeProvider and real PostgreSQL
(catalog-ingestion.md §8, §12): the pool it builds, idempotency, resumability,
failure handling and the report.

Each test starts from an EMPTY catalog: the `empty_catalog` fixture (conftest.py)
deletes all catalog rows inside the test's transaction, which is rolled back
afterwards, so your real pool comes back untouched.
"""

from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import Connection, delete, func, select
from sqlalchemy.orm import Session, sessionmaker

from screening_room.modules.catalog import service
from screening_room.modules.catalog.ingestion.report import build_report
from screening_room.modules.catalog.ingestion.runs import (
    IngestOptions,
    RefreshOptions,
    RunResult,
    run_ingest,
    run_refresh,
)
from screening_room.modules.catalog.models import (
    CandidatePoolMembership,
    Genre,
    IngestionRun,
    Person,
    ProviderTitleRecommendation,
    Title,
    TitleCredit,
    TitleGenre,
)
from screening_room.modules.catalog.providers.base import (
    Credit,
    ListPage,
    ListQuery,
    ProviderGenre,
    ProviderRef,
    TitleDetails,
)
from screening_room.modules.catalog.providers.fake import FakeProvider, fake_title
from screening_room.modules.catalog.providers.tmdb import mapper
from tests.unit.test_tmdb_mapper import fixture

SOURCES = 64  # starter-v1; each has a single page in the fake catalog
GENRE_CHECKS = 2  # one list_genres call per media type


def ref(media: str, provider_id: int) -> ProviderRef:
    return ProviderRef("tmdb", media, provider_id)  # type: ignore[arg-type]


def fake_catalog() -> list[TitleDetails]:
    """A small catalog covering the interesting cases."""
    arrival = replace(
        fake_title(
            "movie",
            101,
            "Arrival",
            genre_ids=(18, 878),
            recommendations=(ref("movie", 102), ref("movie", 999)),  # 999 isn't in our catalog
        ),
        credits=(
            Credit(1, "Amy Adams", None, "cast", "Louise Banks", 0),
            Credit(2, "Denis Villeneuve", None, "director", None, 0),
        ),
    )
    adult = fake_title("movie", 104, "Adult title", genre_ids=(18,))
    return [
        arrival,
        fake_title("movie", 102, "Dune", genre_ids=(878, 12), recommendations=(ref("movie", 101),)),
        fake_title("movie", 103, "Amélie", genre_ids=(35,), original_language="fr", vote_count=300),
        replace(adult, summary=replace(adult.summary, adult=True)),
        fake_title("tv", 201, "The Expanse", genre_ids=(10765, 18)),  # Sci-Fi & Fantasy
        fake_title("tv", 202, "Kingdom", genre_ids=(18,), original_language="ko"),
    ]


def real_genres() -> dict[str, list[ProviderGenre]]:
    return {media: mapper.genres(fixture(f"genres_{media}.json")) for media in ("movie", "tv")}


def make_provider(titles: list[TitleDetails] | None = None) -> FakeProvider:
    return FakeProvider(titles or fake_catalog(), genres=real_genres())  # type: ignore[arg-type]


# --- Fixtures -----------------------------------------------------------------------------


OPEN_SESSIONS: list[int] = [0]


class CountingSession(Session):
    """Counts open sessions, so tests can check none is open during provider calls."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._counted_as_open = True
        OPEN_SESSIONS[0] += 1

    def close(self) -> None:
        if self._counted_as_open:  # close() may run twice; count it once
            self._counted_as_open = False
            OPEN_SESSIONS[0] -= 1
        super().close()


@pytest.fixture
def session_factory(db_session: Session, empty_catalog: None) -> Iterator[sessionmaker[Session]]:
    """Sessions for ingestion, inside the test's rolled-back transaction: their
    commits only release savepoints."""
    connection = db_session.connection()
    assert isinstance(connection, Connection)
    OPEN_SESSIONS[0] = 0
    yield sessionmaker(
        bind=connection,
        class_=CountingSession,
        join_transaction_mode="create_savepoint",
        expire_on_commit=False,
    )


def ingest(
    session_factory: sessionmaker[Session], provider: FakeProvider, **options: Any
) -> RunResult:
    ttl_days = options.pop("ttl_days", 14)
    return run_ingest(
        session_factory, provider, IngestOptions(**options), ttl_days=ttl_days, max_workers=4
    )


# --- Reading the result -------------------------------------------------------------------


def snapshot(session: Session) -> dict[str, Any]:
    """The catalog's content keyed by provider refs (our surrogate ids differ between
    runs), ignoring timestamps and run ids. Equal snapshots = same end state."""
    key = {t.id: (t.media_type, t.provider_id) for t in session.scalars(select(Title))}
    genres = {g.id: g.slug for g in session.scalars(select(Genre))}
    people = {p.id: p.provider_id for p in session.scalars(select(Person))}

    def grouped(rows: Any) -> dict[Any, list[Any]]:
        result: dict[Any, list[Any]] = {}
        for title_id, value in rows:
            result.setdefault(key[title_id], []).append(value)
        return {k: sorted(v) for k, v in sorted(result.items())}

    return {
        "titles": sorted(
            (
                key[t.id],
                t.name,
                t.detail_level,
                t.provider_status,
                t.runtime_minutes,
                t.number_of_seasons,
                t.original_language,
                t.sync_error_count,
            )
            for t in session.scalars(select(Title))
        ),
        "genres": grouped(
            (g.title_id, (g.position, genres[g.genre_id]))
            for g in session.scalars(select(TitleGenre))
        ),
        "credits": grouped(
            (c.title_id, (people[c.person_id], c.role, c.character_name, c.credit_order))
            for c in session.scalars(select(TitleCredit))
        ),
        "memberships": grouped(
            (m.title_id, (m.source_key, m.source_rank))
            for m in session.scalars(select(CandidatePoolMembership))
        ),
        "recommendations": grouped(
            (r.source_title_id, (r.provider_rank, r.target_media_type, r.target_provider_id))
            for r in session.scalars(select(ProviderTitleRecommendation))
        ),
    }


def candidates(session: Session) -> set[tuple[str, int]]:
    return {
        (media, provider_id)
        for media, provider_id in session.execute(
            select(Title.media_type, Title.provider_id).where(service.in_candidate_pool())
        )
    }


# --- Building the pool ----------------------------------------------------------------------


def test_ingest_builds_a_hydrated_pool(session_factory: sessionmaker[Session]) -> None:
    result = ingest(session_factory, make_provider())

    assert result.status == "succeeded", result.error_summary
    with session_factory() as session:
        assert candidates(session) == {
            ("movie", 101),
            ("movie", 102),
            ("movie", 103),
            ("tv", 201),
            ("tv", 202),
        }
        state = snapshot(session)
        run = session.get_one(IngestionRun, result.run_id)
    # The adult title is never stored at all (R18).
    assert ("movie", 104) not in {t[0] for t in state["titles"]}
    # TV "Sci-Fi & Fantasy" maps to two internal genres (in taxonomy order), then
    # the title's next provider genre follows.
    assert state["genres"][("tv", 201)] == [(0, "fantasy"), (1, "science-fiction"), (2, "drama")]
    assert state["credits"][("movie", 101)] == [
        (1, "cast", "Louise Banks", 0),
        (2, "director", None, 0),
    ]
    # Recommendation targets are stored even when they aren't in our catalog.
    assert state["recommendations"][("movie", 101)] == [(1, "movie", 102), (2, "movie", 999)]
    # One title, many sources: one row per source that returned it.
    assert len(state["memberships"][("movie", 101)]) > 1
    assert run.status == "succeeded" and run.finished_at is not None
    assert run.counts["hydrated"] == 5
    assert run.counts["requests"] == GENRE_CHECKS + SOURCES + 5


def test_ingest_is_idempotent(session_factory: sessionmaker[Session]) -> None:
    provider = make_provider()
    ingest(session_factory, provider)
    with session_factory() as session:
        first = snapshot(session)

    # ttl_days=0 makes every title stale, so the second run re-applies everything.
    second_run = ingest(session_factory, provider, ttl_days=0)

    assert second_run.counts["hydrated"] == 5
    with session_factory() as session:
        assert snapshot(session) == first


def test_an_interrupted_run_resumes_to_the_same_end_state(
    session_factory: sessionmaker[Session], db_session: Session
) -> None:
    ingest(session_factory, make_provider())
    with session_factory() as session:
        uninterrupted = snapshot(session)
    db_session.execute(delete(Title))
    db_session.execute(delete(IngestionRun))
    db_session.execute(delete(Person))
    db_session.commit()

    # Stop after discover plus 2 detail requests, as a crash might.
    interrupted = ingest(session_factory, make_provider(), max_requests=GENRE_CHECKS + SOURCES + 2)
    with session_factory() as session:
        summary_only = session.scalar(
            select(func.count()).select_from(Title).where(Title.detail_level == "summary")
        )
    resumed = ingest(session_factory, make_provider())

    assert interrupted.status == "partial"
    # What happened before the stop is still counted (it was lost at first).
    assert interrupted.counts["discovered"] > 0
    assert interrupted.counts["selected"] >= 3
    assert interrupted.counts["requests"] == GENRE_CHECKS + SOURCES + 2
    assert interrupted.error_summary and "budget" in interrupted.error_summary
    assert summary_only and summary_only >= 3  # work was really left over
    assert resumed.status == "succeeded"
    with session_factory() as session:
        assert snapshot(session) == uninterrupted


def test_full_titles_are_never_downgraded(session_factory: sessionmaker[Session]) -> None:
    provider = make_provider()
    ingest(session_factory, provider)
    arrival = provider.get_details(ref("movie", 101))

    with session_factory() as session:
        service.upsert_title_summary(session, arrival.summary, datetime.now(UTC))
        session.commit()
        level = session.scalar(select(Title.detail_level).where(Title.provider_id == 101))

    assert level == "full"


def test_max_titles_caps_the_pool(session_factory: sessionmaker[Session]) -> None:
    result = ingest(session_factory, make_provider(), max_titles=2)

    with session_factory() as session:
        pooled = session.scalar(select(func.count(CandidatePoolMembership.title_id.distinct())))
    assert pooled == 2
    assert result.counts["skipped_by_cap"] > 0


def test_provider_calls_happen_with_no_session_open(
    session_factory: sessionmaker[Session],
) -> None:
    class Checking(FakeProvider):
        def list_titles(self, query: ListQuery, page: int) -> ListPage:
            assert OPEN_SESSIONS[0] == 0, "a session was open while waiting on the provider"
            return super().list_titles(query, page)

    result = ingest(session_factory, Checking(fake_catalog(), genres=real_genres()))  # type: ignore[arg-type]

    assert result.status == "succeeded"


# --- Failures -------------------------------------------------------------------------------


def test_a_404_marks_the_title_missing_and_out_of_the_pool(
    session_factory: sessionmaker[Session],
) -> None:
    provider = make_provider()
    provider.missing.add(ref("tv", 202))

    result = ingest(session_factory, provider)

    assert result.status == "succeeded"  # a vanished title isn't a failed run
    assert result.counts["missing"] == 1
    with session_factory() as session:
        status = session.scalar(select(Title.provider_status).where(Title.provider_id == 202))
        assert ("tv", 202) not in candidates(session)
    assert status == "missing"


def test_failures_make_the_run_partial_and_clear_on_success(
    session_factory: sessionmaker[Session],
) -> None:
    provider = make_provider()
    provider.failing.add(ref("movie", 103))

    first = ingest(session_factory, provider)
    with session_factory() as session:
        errors, message = session.execute(
            select(Title.sync_error_count, Title.last_sync_error).where(Title.provider_id == 103)
        ).one()

    provider.failing.clear()
    second = ingest(session_factory, provider)
    with session_factory() as session:
        errors_after = session.scalar(
            select(Title.sync_error_count).where(Title.provider_id == 103)
        )

    assert first.status == "partial"
    assert (errors, "outage" in (message or "")) == (1, True)
    assert second.status == "succeeded"
    assert errors_after == 0


def test_an_unmapped_provider_genre_stops_the_run_before_any_writes(
    session_factory: sessionmaker[Session],
) -> None:
    genres = real_genres()
    genres["tv"] = [*genres["tv"], ProviderGenre(99999, "Brand New Genre")]
    provider = FakeProvider(fake_catalog(), genres=genres)  # type: ignore[arg-type]

    result = ingest(session_factory, provider)

    assert result.status == "failed"
    assert result.error_summary and "99999" in result.error_summary
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Title)) == 0


def test_an_unmapped_genre_on_a_title_stops_the_run(
    session_factory: sessionmaker[Session],
) -> None:
    oddball = fake_title("movie", 105, "Oddball", genre_ids=(99999,))

    result = ingest(session_factory, make_provider([*fake_catalog(), oddball]))

    assert result.status == "failed"
    assert result.error_summary and "99999" in result.error_summary


def test_a_genre_from_the_other_media_types_list_uses_that_mapping(
    session_factory: sessionmaker[Session],
) -> None:
    # Seen in the first real run: TMDB tagged a TV show with 10749 "Romance",
    # which only TMDB's movie genre list offers.
    show = fake_title("tv", 203, "Romantic show", genre_ids=(10749, 18))

    result = ingest(session_factory, make_provider([*fake_catalog(), show]))

    assert result.status == "succeeded", result.error_summary
    with session_factory() as session:
        assert snapshot(session)["genres"][("tv", 203)] == [(0, "romance"), (1, "drama")]


# --- Refresh and report ---------------------------------------------------------------------


def test_refresh_rehydrates_only_stale_titles(session_factory: sessionmaker[Session]) -> None:
    provider = make_provider()
    ingest(session_factory, provider)
    provider.calls.clear()

    fresh = run_refresh(
        session_factory, provider, RefreshOptions(older_than_days=14), max_workers=2
    )
    everything = run_refresh(
        session_factory, provider, RefreshOptions(older_than_days=0, limit=3), max_workers=2
    )

    assert fresh.counts["hydrated"] == 0  # nothing is older than 14 days
    assert everything.counts["hydrated"] == 3  # all stale, capped by --limit
    assert everything.status == "succeeded"


def test_report_describes_the_pool(session_factory: sessionmaker[Session]) -> None:
    ingest(session_factory, make_provider())

    with session_factory() as session:
        report = build_report(session, now=datetime.now(UTC), ttl_days=14)

    assert "Candidate pool: 5 titles (movie 3, tv 2)" in report
    assert "science-fiction" in report
    assert "ko 1" in report and "fr 1" in report
    # Arrival recommends Dune (a candidate) and 999 (unknown): half resolve; Dune
    # recommends Arrival: all resolve. 2 of 3 targets overall.
    assert "targets that are themselves candidates: 67%" in report
    assert "Latest run: #" in report and "succeeded" in report
