"""The engine's entry point: profile -> eligibility -> scoring -> ranking -> explanation.

recommend() is a pure function of its arguments (recommendation-engine.md §2):
the same inputs always give the same outcome, whatever order they arrive in.
"""

from collections.abc import Iterable, Mapping
from datetime import date

from screening_room.modules.discovery.engine import eligibility, ranking, scoring
from screening_room.modules.discovery.engine.config import EngineConfig
from screening_room.modules.discovery.engine.explain import explain
from screening_room.modules.discovery.engine.profile import build_profile
from screening_room.modules.discovery.engine.types import (
    Candidate,
    Diagnostics,
    NeighborIndex,
    Notice,
    PoolStats,
    RecommendationContext,
    RecommendationOutcome,
    Result,
    UserSignals,
)

COLD_START_TEXT = "Recommendations improve as you pick favorites, rate and dismiss titles."


def recommend(
    signals: UserSignals,
    context: RecommendationContext,
    candidates: Iterable[Candidate],
    pool_stats: PoolStats,
    neighbor_index: NeighborIndex,
    genre_names: Mapping[int, str],
    config: EngineConfig,
    as_of: date,
) -> RecommendationOutcome:
    all_candidates = list(candidates)
    profile = build_profile(signals, config)
    eligible, rejected = eligibility.check(
        all_candidates, eligibility.EligibilityInput(context, signals, as_of)
    )
    scored = scoring.score_all(eligible, profile, pool_stats, neighbor_index, config)
    selected, relaxed = ranking.rank(scored, context, config)

    results = tuple(
        Result(
            rank=position,
            title_id=item.candidate.title_id,
            score=round(item.score, 6),
            breakdown=item.breakdown,
            reasons=explain(item, profile, context, genre_names, config),
        )
        for position, item in enumerate(selected, start=1)
    )

    # An anchor with no eligible neighbor contributes nothing (§7.1): count them.
    eligible_ids = frozenset(c.title_id for c in eligible)
    anchors_with_neighbors = {
        source.anchor_title_id
        for anchor in profile.anchors
        for _, source in scoring.best_neighbor_sources(
            [anchor], neighbor_index, eligible_ids, config
        ).values()
    }

    notices: list[Notice] = []
    if profile.is_empty:
        notices.append(Notice("cold_start", COLD_START_TEXT))
    if len(results) < context.limit:
        notices.append(Notice("few_results", _few_results_text(len(results), context)))

    return RecommendationOutcome(
        results=results,
        rejected=tuple(rejected),
        cold_start=profile.is_empty,
        diversity_relaxed=relaxed,
        notices=tuple(notices),
        diagnostics=Diagnostics(
            candidate_count=len(all_candidates),
            eligible_count=len(eligible),
            anchor_count=len(profile.anchors),
            anchors_without_neighbors=len(profile.anchors) - len(anchors_with_neighbors),
        ),
    )


def _few_results_text(count: int, context: RecommendationContext) -> str:
    """Never pad with ineligible titles; suggest relaxing a filter instead (§10).

    Filters are only mentioned when some were set (1.1.1). Without any, a short
    list means "show me more" ran out, or there's little to recommend yet.
    """
    titles = f"{count} title" if count == 1 else f"{count} titles"
    if context.max_runtime_minutes is not None:
        hint = "Try a longer runtime."
    elif context.genre_ids:
        hint = "Try fewer genres."
    elif context.media_type != "any":
        hint = "Try including both movies and TV."
    elif context.exclude_title_ids:  # no filters: "show me more" ran out
        return "No more titles to show." if count == 0 else f"Only {titles} more to show."
    else:  # no filters, nothing excluded
        return (
            "There's nothing to recommend yet."
            if count == 0
            else f"Only {titles} to recommend right now."
        )
    found = (
        "No titles match" if count == 0 else f"Only {titles} {'matches' if count == 1 else 'match'}"
    )
    return f"{found} your filters. {hint}"
