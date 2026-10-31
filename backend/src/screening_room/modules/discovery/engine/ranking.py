"""Stage 4: ranking and diversity (recommendation-engine.md §8).

1. Stable order: (-round(score, 6), title_id).
2. Fill the slots greedily, skipping a candidate that would break a rule:
   (a) no genre in more than 3 results; a title counts towards EVERY genre it
       has (no "primary genre"). Genres the user asked for are exempt.
   (b) at most 1 result per identical genre set (near-duplicate guard).
3. If slots are still empty, fill them from the skipped ones in score order and
   report diversity_relaxed.
"""

from collections import Counter

from screening_room.modules.discovery.engine.config import EngineConfig
from screening_room.modules.discovery.engine.types import RecommendationContext, ScoredCandidate


def ordered(scored: list[ScoredCandidate]) -> list[ScoredCandidate]:
    return sorted(scored, key=lambda s: (-round(s.score, 6), s.candidate.title_id))


def rank(
    scored: list[ScoredCandidate], context: RecommendationContext, config: EngineConfig
) -> tuple[list[ScoredCandidate], bool]:
    """The chosen results, best first, and whether the diversity rules had to relax."""
    selected: list[ScoredCandidate] = []
    skipped: list[ScoredCandidate] = []
    per_genre: Counter[int] = Counter()
    per_genre_set: Counter[frozenset[int]] = Counter()

    for item in ordered(scored):
        if len(selected) == context.limit:
            break
        genres = item.candidate.genre_ids
        capped_genres = genres - context.genre_ids  # requested genres are exempt
        too_many_of_a_genre = any(
            per_genre[g] >= config.max_results_per_genre for g in capped_genres
        )
        near_duplicate = per_genre_set[genres] >= config.max_results_per_genre_set
        if too_many_of_a_genre or near_duplicate:
            skipped.append(item)
            continue
        selected.append(item)
        per_genre.update(capped_genres)
        per_genre_set[genres] += 1

    relaxed = False
    for item in skipped:  # already in score order
        if len(selected) == context.limit:
            break
        selected.append(item)
        relaxed = True
    return selected, relaxed
