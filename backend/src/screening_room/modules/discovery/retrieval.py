"""Stage 1, retrieval: the engine's inputs from the database (recommendation-engine.md §5).

The only stage that does I/O, and it reads the local database only (never TMDB).
It uses the catalog's and profile's PUBLIC functions (ADR-0001), then maps their
DTOs to the engine's types, so the engine never sees the database.
"""

from collections.abc import Mapping
from dataclasses import dataclass

from sqlalchemy.orm import Session

from screening_room.modules.catalog import service as catalog
from screening_room.modules.discovery.engine.types import (
    Candidate,
    Favorite,
    Neighbor,
    NeighborIndex,
    PoolStats,
    UserSignals,
)
from screening_room.modules.profile import service as profile


@dataclass(frozen=True)
class EngineInputs:
    signals: UserSignals
    candidates: tuple[Candidate, ...]
    pool_stats: PoolStats
    neighbor_index: NeighborIndex
    genre_names: Mapping[int, str]


def retrieve(session: Session, user_id: int) -> EngineInputs:
    taste = profile.taste_signals(session, user_id)
    favorite_info = catalog.titles_with_genres(session, taste.favorite_title_ids)
    favorites = tuple(
        Favorite(
            title_id=pick.title_id,
            name=favorite_info[pick.title_id][0],
            genre_ids=favorite_info[pick.title_id][1],
            picked_at=pick.picked_at,
        )
        for pick in taste.favorite_picks
        if pick.title_id in favorite_info
    )
    candidates = tuple(
        Candidate(
            title_id=c.title_id,
            media_type=c.media_type,
            genre_ids=c.genre_ids,
            runtime_minutes=c.runtime_minutes,
            release_date=c.release_date,
            vote_average=c.vote_average,
            vote_count=c.vote_count,
            popularity=c.popularity,
            source_keys=c.source_keys,
        )
        for c in catalog.pool_candidates(session)
    )
    neighbors = catalog.pool_neighbors(session, (f.title_id for f in favorites))
    return EngineInputs(
        signals=UserSignals(
            liked_genre_ids=taste.liked_genre_ids,
            avoided_genre_ids=taste.avoided_genre_ids,
            favorites=favorites,
        ),
        candidates=candidates,
        pool_stats=pool_stats(candidates),
        neighbor_index={
            anchor: tuple(Neighbor(title_id, rank) for title_id, rank in entries)
            for anchor, entries in neighbors.items()
        },
        genre_names=catalog.genre_names(session),
    )


def pool_stats(candidates: tuple[Candidate, ...]) -> PoolStats:
    """C (mean rating) and max popularity from the same data as the candidates (§5)."""
    ratings = [c.vote_average for c in candidates if c.vote_average is not None]
    return PoolStats(
        mean_vote_average=sum(ratings) / len(ratings) if ratings else 0.0,
        max_popularity=max((c.popularity or 0.0 for c in candidates), default=0.0),
        pool_size=len(candidates),
    )
