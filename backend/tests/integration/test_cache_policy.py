"""TMDB data is cached for at most 6 months (API Terms of Use §1.C): `prune` removes
old titles nobody uses, and `refresh` keeps every other stored title fresh."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from screening_room.modules.catalog import service
from screening_room.modules.catalog.ingestion.prune import prune_outside_pool
from screening_room.modules.catalog.ingestion.runs import RefreshOptions, run_refresh
from screening_room.modules.catalog.models import IngestionRun, Title
from screening_room.modules.catalog.providers.base import TitleDetails
from screening_room.modules.catalog.providers.fake import FakeProvider, fake_title
from screening_room.modules.identity.models import User
from screening_room.modules.library import service as library
from tests.integration.test_ingestion import real_genres, session_factory  # noqa: F401

NOW = datetime.now(UTC)
OLD = NOW - timedelta(days=200)  # older than 6 months
RECENT = NOW - timedelta(days=2)


def store(
    session: Session, details: TitleDetails, synced_at: datetime, *, full: bool, pool: bool
) -> int:
    title_id = service.upsert_title_summary(session, details.summary, synced_at)
    run = IngestionRun(command="ingest", params={}, status="succeeded", counts={})
    session.add(run)
    session.flush()
    if full:
        genre_map = service.load_genre_map(session, "tmdb")
        service.apply_title_details(session, title_id, details, genre_map, run.id, synced_at)
    if pool:
        service.upsert_pool_membership(session, title_id, "test:source", 1, run.id)
    return title_id


def test_prune_deletes_old_unused_titles_outside_the_pool_only(
    session_factory: sessionmaker[Session],  # noqa: F811
) -> None:
    with session_factory() as session:
        old_unused = store(
            session, fake_title("movie", 1, "Old Unused"), OLD, full=False, pool=False
        )
        old_in_use = store(session, fake_title("movie", 2, "Old Rated"), OLD, full=True, pool=False)
        recent = store(session, fake_title("movie", 3, "Recent"), RECENT, full=False, pool=False)
        in_pool = store(session, fake_title("movie", 4, "Old Pool"), OLD, full=True, pool=True)
        user = User(email="cache@example.com", password_hash="not-a-real-hash")
        session.add(user)
        session.flush()
        library.rate(session, user.id, old_in_use, 4)  # a user still references it
        session.commit()

    counts = prune_outside_pool(session_factory, older_than=NOW - timedelta(days=30))

    assert (counts.candidates, counts.deleted, counts.kept_in_use) == (2, 1, 1)
    with session_factory() as session:
        remaining = set(session.scalars(select(Title.id)))
    assert old_unused not in remaining
    assert {old_in_use, recent, in_pool} <= remaining


def test_refresh_also_covers_titles_outside_the_pool(
    session_factory: sessionmaker[Session],  # noqa: F811
) -> None:
    searched = fake_title("movie", 11, "Searched Long Ago")
    picked = fake_title("tv", 12, "Picked Long Ago")
    fresh = fake_title("movie", 13, "Fresh")
    with session_factory() as session:
        searched_id = store(session, searched, OLD, full=False, pool=False)  # summary only
        picked_id = store(session, picked, OLD, full=True, pool=False)
        fresh_id = store(session, fresh, RECENT, full=True, pool=False)
        session.commit()
    provider = FakeProvider([searched, picked, fresh], genres=real_genres())  # type: ignore[arg-type]

    result = run_refresh(
        session_factory, provider, RefreshOptions(older_than_days=14), max_workers=2
    )

    assert result.counts["hydrated"] == 2
    with session_factory() as session:
        synced = {
            title.id: (title.detail_level, title.details_synced_at)
            for title in session.scalars(
                select(Title).where(Title.id.in_([searched_id, picked_id, fresh_id]))
            )
        }
    assert synced[searched_id][0] == "full"  # now hydrated
    for title_id in (searched_id, picked_id):
        refreshed_at = synced[title_id][1]
        assert refreshed_at is not None and refreshed_at > NOW - timedelta(minutes=5)
    untouched_at = synced[fresh_id][1]
    assert untouched_at is not None and untouched_at < NOW - timedelta(days=1)  # not refetched
