"""The catalog schema against real PostgreSQL: taxonomy, constraints, cascades and
the candidate pool rule (data-model.md §3.2 and §4, catalog-ingestion.md §4.2).

Queries are scoped to rows each test creates, so they hold whatever else the
database contains (e.g. a real ingested pool).
"""

from collections.abc import Iterator
from datetime import UTC, datetime
from itertools import count
from typing import Any

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from screening_room.modules.catalog.models import (
    CandidatePoolMembership,
    Genre,
    IngestionRun,
    Person,
    ProviderGenreMap,
    ProviderTitleRecommendation,
    Title,
    TitleCredit,
    TitleGenre,
)
from screening_room.modules.catalog.service import in_candidate_pool

NOW = datetime.now(UTC)
# Provider IDs far from real TMDB IDs, unique within a test run.
_provider_ids: Iterator[int] = count(900_000_000)


def make_title(db_session: Session, **overrides: Any) -> Title:
    """A valid, fully hydrated movie; override any column."""
    values: dict[str, Any] = {
        "provider": "tmdb",
        "media_type": "movie",
        "provider_id": next(_provider_ids),
        "name": "Test Title",
        "detail_level": "full",
        "details_synced_at": NOW,
    }
    title = Title(**(values | overrides))
    db_session.add(title)
    db_session.flush()
    return title


def make_run(db_session: Session) -> IngestionRun:
    run = IngestionRun(command="ingest", params={}, status="running", counts={})
    db_session.add(run)
    db_session.flush()
    return run


def add_to_pool(db_session: Session, title: Title, run: IngestionRun) -> None:
    db_session.add(
        CandidatePoolMembership(
            title_id=title.id,
            source_key="movie:popular",
            source_rank=1,
            first_seen_run_id=run.id,
            last_seen_run_id=run.id,
        )
    )
    db_session.flush()


def genre_id(db_session: Session, slug: str) -> int:
    return db_session.scalars(select(Genre.id).where(Genre.slug == slug)).one()


# --- Genre taxonomy (reference data loaded by migration 0003) ---------------------------


def mapped_slugs(db_session: Session, media_type: str, provider_genre_id: int) -> set[str]:
    return set(
        db_session.scalars(
            select(Genre.slug)
            .join(ProviderGenreMap, ProviderGenreMap.genre_id == Genre.id)
            .where(
                ProviderGenreMap.provider == "tmdb",
                ProviderGenreMap.media_type == media_type,
                ProviderGenreMap.provider_genre_id == provider_genre_id,
            )
        )
    )


@pytest.mark.parametrize(
    ("media_type", "provider_genre_id", "expected"),
    [
        ("movie", 28, {"action"}),
        ("movie", 878, {"science-fiction"}),
        ("movie", 10751, {"family"}),
        # TV merges genres that movies keep apart: one maps to several internal genres.
        ("tv", 10759, {"action", "adventure"}),
        ("tv", 10765, {"science-fiction", "fantasy"}),
        ("tv", 10768, {"war", "politics"}),
        ("tv", 10762, {"kids"}),  # kept separate from family
    ],
)
def test_tmdb_genres_map_to_internal_genres(
    db_session: Session, media_type: str, provider_genre_id: int, expected: set[str]
) -> None:
    assert mapped_slugs(db_session, media_type, provider_genre_id) == expected


def test_every_tmdb_genre_is_mapped(db_session: Session) -> None:
    rows = db_session.execute(
        select(
            ProviderGenreMap.media_type,
            func.count(ProviderGenreMap.provider_genre_id.distinct()),
        )
        .where(ProviderGenreMap.provider == "tmdb")
        .group_by(ProviderGenreMap.media_type)
    )
    counts = {media_type: n for media_type, n in rows}

    # TMDB's full genre lists: 19 for movies, 16 for TV.
    assert counts == {"movie": 19, "tv": 16}


def test_every_internal_genre_is_reachable_from_tmdb(db_session: Session) -> None:
    unmapped = db_session.scalars(
        select(Genre.slug).where(~Genre.id.in_(select(ProviderGenreMap.genre_id)))
    ).all()

    assert unmapped == []


# --- Constraints ------------------------------------------------------------------------


def test_the_same_tmdb_id_can_be_a_movie_and_a_tv_show(db_session: Session) -> None:
    # TMDB IDs are unique only per media type (ADR-0004).
    movie = make_title(db_session, media_type="movie")

    make_title(db_session, media_type="tv", provider_id=movie.provider_id)  # no error


def test_a_provider_ref_can_only_exist_once(db_session: Session) -> None:
    title = make_title(db_session)

    with pytest.raises(IntegrityError, match="uq_titles_provider_media_type_provider_id"):
        make_title(db_session, provider_id=title.provider_id)


@pytest.mark.parametrize(
    ("overrides", "constraint"),
    [
        ({"media_type": "anime"}, "ck_titles_media_type_valid"),
        ({"provider": "imdb"}, "ck_titles_provider_valid"),
        ({"detail_level": "partial"}, "ck_titles_detail_level_valid"),
        ({"provider_status": "deleted"}, "ck_titles_provider_status_valid"),
        ({"runtime_minutes": 0}, "ck_titles_runtime_positive"),
        ({"media_type": "movie", "number_of_seasons": 2}, "ck_titles_seasons_only_for_tv"),
        ({"vote_average": 10.5}, "ck_titles_vote_average_range"),
        ({"vote_count": -1}, "ck_titles_vote_count_not_negative"),
        (
            {"detail_level": "full", "details_synced_at": None},
            "ck_titles_full_has_details_synced_at",
        ),
    ],
)
def test_invalid_titles_are_rejected(
    db_session: Session, overrides: dict[str, Any], constraint: str
) -> None:
    with pytest.raises(IntegrityError, match=constraint):
        make_title(db_session, **overrides)


def test_tv_titles_may_have_seasons(db_session: Session) -> None:
    make_title(db_session, media_type="tv", number_of_seasons=3)  # no error


def test_a_summary_title_needs_no_details_sync_time(db_session: Session) -> None:
    make_title(db_session, detail_level="summary", details_synced_at=None)  # no error


def test_unknown_credit_role_is_rejected(db_session: Session) -> None:
    title = make_title(db_session)
    person = Person(provider="tmdb", provider_id=next(_provider_ids), name="Someone")
    db_session.add(person)
    db_session.flush()

    db_session.add(
        TitleCredit(title_id=title.id, person_id=person.id, role="producer", credit_order=0)
    )
    with pytest.raises(IntegrityError, match="ck_title_credits_role_valid"):
        db_session.flush()


# --- Deleting a title -------------------------------------------------------------------


def test_deleting_a_title_removes_its_child_rows(db_session: Session) -> None:
    title = make_title(db_session)
    run = make_run(db_session)
    person = Person(provider="tmdb", provider_id=next(_provider_ids), name="Someone")
    db_session.add(person)
    db_session.flush()
    add_to_pool(db_session, title, run)
    db_session.add_all(
        [
            TitleGenre(title_id=title.id, genre_id=genre_id(db_session, "drama"), position=0),
            TitleCredit(title_id=title.id, person_id=person.id, role="cast", credit_order=0),
            ProviderTitleRecommendation(
                source_title_id=title.id,
                provider="tmdb",
                target_media_type="movie",
                target_provider_id=123,
                provider_rank=1,
                fetched_at=NOW,
                ingestion_run_id=run.id,
            ),
        ]
    )
    db_session.flush()

    db_session.execute(delete(Title).where(Title.id == title.id))

    for model, column in [
        (TitleGenre, TitleGenre.title_id),
        (TitleCredit, TitleCredit.title_id),
        (CandidatePoolMembership, CandidatePoolMembership.title_id),
        (ProviderTitleRecommendation, ProviderTitleRecommendation.source_title_id),
    ]:
        remaining = db_session.scalar(
            select(func.count()).select_from(model).where(column == title.id)
        )
        assert remaining == 0, f"{model.__tablename__} rows survived the delete"
    # People are shared between titles, so they stay.
    assert db_session.get(Person, person.id) is not None


def test_a_genre_in_use_cannot_be_deleted(db_session: Session) -> None:
    # A throwaway genre used only by a title, so the only thing that can block the
    # delete is title_genres (real genres are also referenced by the TMDB mapping).
    genre = Genre(slug="test-only-genre", name="Test only")
    db_session.add(genre)
    db_session.flush()
    db_session.add(TitleGenre(title_id=make_title(db_session).id, genre_id=genre.id, position=0))
    db_session.flush()

    with pytest.raises(IntegrityError, match="fk_title_genres_genre_id_genres"):
        db_session.execute(delete(Genre).where(Genre.id == genre.id))


# --- The candidate pool (data-model.md §4) ------------------------------------------------


def test_only_pooled_full_active_non_adult_titles_are_candidates(db_session: Session) -> None:
    run = make_run(db_session)
    candidate = make_title(db_session, name="candidate")
    not_pooled = make_title(db_session, name="not pooled")  # e.g. only ever viewed or searched
    summary_only = make_title(
        db_session, name="summary only", detail_level="summary", details_synced_at=None
    )
    missing = make_title(db_session, name="missing at provider", provider_status="missing")
    adult = make_title(db_session, name="adult", adult=True)
    for title in (candidate, summary_only, missing, adult):
        add_to_pool(db_session, title, run)
    ours = [candidate.id, not_pooled.id, summary_only.id, missing.id, adult.id]

    selected = db_session.scalars(
        select(Title.name).where(Title.id.in_(ours), in_candidate_pool())
    ).all()

    assert selected == ["candidate"]


def test_a_title_in_several_sources_is_still_one_candidate(db_session: Session) -> None:
    run = make_run(db_session)
    title = make_title(db_session)
    add_to_pool(db_session, title, run)
    db_session.add(
        CandidatePoolMembership(
            title_id=title.id,
            source_key="movie:top_rated",
            source_rank=4,
            first_seen_run_id=run.id,
            last_seen_run_id=run.id,
        )
    )
    db_session.flush()

    selected = db_session.scalars(
        select(Title.id).where(Title.id == title.id, in_candidate_pool())
    ).all()

    assert selected == [title.id]
