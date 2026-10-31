"""Stage 3: scoring (recommendation-engine.md §7).

    score = 0.45 affinity + 0.25 favorite_neighbor + 0.20 quality + 0.10 popularity

Every signal is computed for every eligible candidate; favorite_neighbor is a
supporting signal, not a separate path (§7.1).
"""

import math
from collections.abc import Iterable, Mapping

from screening_room.modules.discovery.engine.config import EngineConfig
from screening_room.modules.discovery.engine.types import (
    Anchor,
    Candidate,
    NeighborIndex,
    NeighborSource,
    PoolStats,
    ScoreBreakdown,
    ScoredCandidate,
    SignalScore,
    TasteProfile,
)


def affinity(candidate: Candidate, genre_weights: Mapping[int, float]) -> float:
    """Cosine similarity between the title's genres (0/1 each) and the user's signed
    genre weights, in [-1, 1]. 0 when either side has nothing to compare."""
    user_norm = math.sqrt(sum(w * w for w in genre_weights.values()))
    if user_norm == 0 or not candidate.genre_ids:
        return 0.0
    dot = sum(genre_weights.get(genre_id, 0.0) for genre_id in candidate.genre_ids)
    return dot / (math.sqrt(len(candidate.genre_ids)) * user_norm)


def quality(candidate: Candidate, stats: PoolStats, config: EngineConfig) -> float:
    """Bayesian average / 10: few votes pull the rating towards the pool mean C."""
    votes = candidate.vote_count or 0
    rating = (
        candidate.vote_average if candidate.vote_average is not None else stats.mean_vote_average
    )
    m = config.quality_prior_votes
    bayesian = (votes / (votes + m)) * rating + (m / (votes + m)) * stats.mean_vote_average
    return min(max(bayesian / 10, 0.0), 1.0)


def popularity(candidate: Candidate, stats: PoolStats) -> float:
    """log-scaled against the pool's most popular title, in [0, 1]."""
    if stats.max_popularity <= 0 or not candidate.popularity:
        return 0.0
    return min(math.log1p(candidate.popularity) / math.log1p(stats.max_popularity), 1.0)


def best_neighbor_sources(
    anchors: Iterable[Anchor],
    neighbor_index: NeighborIndex,
    eligible_ids: frozenset[int],
    config: EngineConfig,
) -> dict[int, tuple[float, NeighborSource]]:
    """For each eligible candidate in some anchor's list: its favorite_neighbor value,
    and the anchor credited. Value = anchor weight x (1 - (rank - 1) / 20).

    Ties: higher value, then lower provider rank, then lower anchor title id.
    """
    best: dict[int, tuple[float, NeighborSource]] = {}
    for anchor in anchors:
        for neighbor in neighbor_index.get(anchor.title_id, ()):
            if neighbor.title_id not in eligible_ids:
                continue
            decay = 1 - (neighbor.provider_rank - 1) / config.neighbor_rank_span
            value = max(anchor.weight * decay, 0.0)
            source = NeighborSource(
                anchor_title_id=anchor.title_id,
                anchor_name=anchor.name,
                anchor_kind=anchor.kind,
                provider_rank=neighbor.provider_rank,
                anchor_stars=anchor.stars,
            )
            current = best.get(neighbor.title_id)
            if current is None or _rank_key(value, source) < _rank_key(*current):
                best[neighbor.title_id] = (value, source)
    return best


def _rank_key(value: float, source: NeighborSource) -> tuple[float, int, int]:
    return (-round(value, 9), source.provider_rank, source.anchor_title_id)


def score_all(
    eligible: Iterable[Candidate],
    profile: TasteProfile,
    stats: PoolStats,
    neighbor_index: NeighborIndex,
    config: EngineConfig,
) -> list[ScoredCandidate]:
    candidates = sorted(eligible, key=lambda c: c.title_id)
    eligible_ids = frozenset(c.title_id for c in candidates)
    neighbors = best_neighbor_sources(profile.anchors, neighbor_index, eligible_ids, config)

    scored = []
    for candidate in candidates:
        neighbor_value, source = neighbors.get(candidate.title_id, (0.0, None))
        values = {
            "affinity": (affinity(candidate, profile.genre_weights), config.weight_affinity),
            "favorite_neighbor": (neighbor_value, config.weight_favorite_neighbor),
            "quality": (quality(candidate, stats, config), config.weight_quality),
            "popularity": (popularity(candidate, stats), config.weight_popularity),
        }
        signals = {name: SignalScore(v, v * weight) for name, (v, weight) in values.items()}
        scored.append(
            ScoredCandidate(
                candidate=candidate,
                breakdown=ScoreBreakdown(
                    affinity=signals["affinity"],
                    favorite_neighbor=signals["favorite_neighbor"],
                    quality=signals["quality"],
                    popularity=signals["popularity"],
                    neighbor_source=source,
                ),
            )
        )
    return scored
