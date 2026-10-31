"""Stage 5: explanations (recommendation-engine.md §9).

Up to 2 reasons per result, at least 1:
1. one PERSONAL reason, only if its signal really contributed (a threshold on its
   weighted score). favorite_neighbor is preferred over genre_affinity whenever
   it qualifies: it's the more specific, title-level reason (decided in M3; a
   favorite's neighbors usually share its genres, so "largest contribution"
   would almost never show it);
2. one context or quality reason (context_genre, runtime_fit, well_rated);
3. with no personal reason: up to 2 of those; with nothing at all: pool_source.

Reasons state only facts from the inputs. "Because you picked Arrival" is true:
the user picked it and the score used that link. We never claim *why* TMDB
relates two titles ("similar tone", "same director").
"""

from collections.abc import Mapping

from screening_room.modules.discovery.engine.config import EngineConfig
from screening_room.modules.discovery.engine.types import (
    Candidate,
    Reason,
    RecommendationContext,
    ScoredCandidate,
    TasteProfile,
)


def explain(
    item: ScoredCandidate,
    profile: TasteProfile,
    context: RecommendationContext,
    genre_names: Mapping[int, str],
    config: EngineConfig,
) -> tuple[Reason, ...]:
    personal = _personal_reasons(item, profile, genre_names, config)
    other = _context_and_quality_reasons(item, context, genre_names, config)
    reasons = other[: config.max_reasons]
    if personal:  # one personal reason first, then one context or quality reason
        reasons = [personal[0], *other[:1]]
    if not reasons:
        reasons = [pool_source_reason(item.candidate)]
    return tuple(reasons[: config.max_reasons])


def _personal_reasons(
    item: ScoredCandidate,
    profile: TasteProfile,
    genre_names: Mapping[int, str],
    config: EngineConfig,
) -> list[Reason]:
    """Qualifying personal reasons, in preference order: favorite link first."""
    breakdown = item.breakdown
    reasons: list[Reason] = []

    source = breakdown.neighbor_source
    if source and breakdown.favorite_neighbor.weighted >= config.min_neighbor_contribution:
        text = (
            f"Because you rated {source.anchor_name} {source.anchor_stars}★"
            if source.anchor_kind == "rated"
            else f"Because you picked {source.anchor_name}"
        )
        reasons.append(
            Reason("favorite_neighbor", text, {"anchor_title_id": source.anchor_title_id})
        )

    liked = [g for g in item.candidate.genre_ids if profile.genre_weights.get(g, 0) > 0]
    if liked and breakdown.affinity.weighted >= config.min_affinity_contribution:
        top = sorted(liked, key=lambda g: (-profile.genre_weights[g], g))[:2]
        names = ", ".join(genre_names.get(g, "?") for g in top)
        # "your taste", not "genres you like": favorites add weight to their genres
        # too, so the user may never have chosen these genres themselves.
        reasons.append(Reason("genre_affinity", f"Matches your taste: {names}"))
    return reasons


def _context_and_quality_reasons(
    item: ScoredCandidate,
    context: RecommendationContext,
    genre_names: Mapping[int, str],
    config: EngineConfig,
) -> list[Reason]:
    candidate = item.candidate
    reasons: list[Reason] = []

    matched = sorted(genre_names.get(g, "?") for g in candidate.genre_ids & context.genre_ids)
    if matched:
        reasons.append(Reason("context_genre", f"Matches your pick: {', '.join(matched[:2])}"))

    if (
        context.max_runtime_minutes is not None
        and candidate.media_type == "movie"
        and candidate.runtime_minutes is not None
    ):
        reasons.append(
            Reason("runtime_fit", f"Fits your time: {format_runtime(candidate.runtime_minutes)}")
        )

    if (
        item.breakdown.quality.value >= config.min_quality_for_well_rated
        and candidate.vote_average is not None
        and candidate.vote_count
    ):
        reasons.append(
            Reason(
                "well_rated",
                f"Rated {candidate.vote_average:.1f}/10 by {candidate.vote_count:,} TMDB users",
            )
        )
    return reasons


def pool_source_reason(candidate: Candidate) -> Reason:
    """Always available and always true: which seed source put it in the pool."""
    kind = "movies" if candidate.media_type == "movie" else "TV shows"
    keys = candidate.source_keys
    if any(key.endswith(":top_rated") for key in keys):
        text = f"Among TMDB's top-rated {kind}"
    elif any(key.endswith(":popular") for key in keys):
        text = "Popular on TMDB"
    else:
        text = f"Among TMDB's most-voted {kind}"
    return Reason("pool_source", text)


def format_runtime(minutes: int) -> str:
    """116 -> "1h 56m"."""
    hours, rest = divmod(minutes, 60)
    if hours == 0:
        return f"{rest}m"
    return f"{hours}h" if rest == 0 else f"{hours}h {rest}m"
