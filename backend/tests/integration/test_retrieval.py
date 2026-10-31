"""Retrieval: the engine's inputs from the real database (recommendation-engine.md §5).

Starts from an EMPTY catalog (conftest.py), so the pool is exactly what each test adds.
"""

from datetime import UTC, date, datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from screening_room.modules.catalog.models import ProviderTitleRecommendation, Title
from screening_room.modules.discovery.engine.config import EngineConfig
from screening_room.modules.discovery.engine.pipeline import recommend
from screening_room.modules.discovery.engine.types import Neighbor, RecommendationContext
from screening_room.modules.discovery.retrieval import retrieve
from screening_room.modules.identity.models import User
from screening_room.modules.profile import service as profile
from screening_room.modules.profile.schemas import PreferencesIn
from tests.integration.helpers import add_candidate, genre_id

RELEASED = date(2016, 11, 10)  # the recommender skips unreleased titles


def provider_id(db_session: Session, title_id: int) -> int:
    return db_session.scalars(select(Title.provider_id).where(Title.id == title_id)).one()


def recommends(db_session: Session, source: int, targets: list[int]) -> None:
    """Store a TMDB-style recommendation list for `source`, ranks 1..n."""
    db_session.add_all(
        ProviderTitleRecommendation(
            source_title_id=source,
            provider="tmdb",
            target_media_type="movie",
            target_provider_id=target,
            provider_rank=rank,
            fetched_at=datetime.now(UTC),
        )
        for rank, target in enumerate(targets, start=1)
    )
    db_session.commit()


def test_retrieval_builds_engine_inputs_from_the_pool(
    db_session: Session, empty_catalog: None
) -> None:
    favorite = add_candidate(db_session, "Arrival", genre_ids=(18, 878), release_date=RELEASED)
    neighbor_a = add_candidate(db_session, "Dune", genre_ids=(878, 12), release_date=RELEASED)
    neighbor_b = add_candidate(db_session, "Contact", genre_ids=(878,), release_date=RELEASED)
    missing = add_candidate(db_session, "Gone")
    db_session.execute(update(Title).where(Title.id == missing).values(provider_status="missing"))
    recommends(
        db_session,
        favorite,
        [
            provider_id(db_session, missing),  # rank 1: not in the pool any more
            provider_id(db_session, neighbor_a),  # rank 2
            999_999_999,  # rank 3: not in our catalog at all
            provider_id(db_session, neighbor_b),  # rank 4
        ],
    )
    user = User(email="retrieval@example.com", password_hash="not-a-real-hash")
    db_session.add(user)
    db_session.flush()
    drama = genre_id(db_session, "drama")
    profile.replace_preferences(db_session, user.id, PreferencesIn(liked_genre_ids=[drama]))
    profile.add_favorite(db_session, user.id, favorite)
    db_session.commit()

    inputs = retrieve(db_session, user.id)

    assert {c.title_id for c in inputs.candidates} == {favorite, neighbor_a, neighbor_b}
    assert inputs.pool_stats.pool_size == 3
    # Only pool titles survive, with TMDB's ranks kept.
    assert inputs.neighbor_index == {favorite: (Neighbor(neighbor_a, 2), Neighbor(neighbor_b, 4))}
    assert inputs.signals.liked_genre_ids == frozenset({drama})
    [pick] = inputs.signals.favorites
    assert (pick.title_id, pick.name) == (favorite, "Arrival")
    assert pick.genre_ids == frozenset({drama, genre_id(db_session, "science-fiction")})
    assert inputs.genre_names[drama] == "Drama"
    # Candidates carry their seed sources (for the pool_source reason).
    assert all(c.source_keys for c in inputs.candidates)

    # End to end through the engine: real rows produce a "Because you picked" reason.
    outcome = recommend(
        inputs.signals,
        RecommendationContext(),
        inputs.candidates,
        inputs.pool_stats,
        inputs.neighbor_index,
        inputs.genre_names,
        EngineConfig(),
        datetime.now(UTC).date(),
    )
    texts = {r.title_id: [reason.text for reason in r.reasons] for r in outcome.results}
    assert favorite not in texts  # never recommend a favorite back
    assert texts[neighbor_a][0] == "Because you picked Arrival"
    assert outcome.diagnostics.anchors_without_neighbors == 0


def test_a_user_with_no_profile_gets_empty_signals(
    db_session: Session, empty_catalog: None
) -> None:
    add_candidate(db_session, "Lonely")
    user = User(email="nobody@example.com", password_hash="not-a-real-hash")
    db_session.add(user)
    db_session.commit()

    inputs = retrieve(db_session, user.id)

    assert inputs.signals.favorites == ()
    assert inputs.neighbor_index == {}
    assert inputs.pool_stats.pool_size == 1
