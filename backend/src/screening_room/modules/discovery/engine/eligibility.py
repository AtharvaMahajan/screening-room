"""Stage 2: eligibility (recommendation-engine.md §6).

Each rule returns None (keep) or a Rejection. The core re-checks everything,
even what retrieval already filtered in SQL, so its guarantees don't depend on
a query. Rules run in list order; the first that rejects is recorded.
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date

from screening_room.modules.discovery.engine.types import (
    Candidate,
    RecommendationContext,
    Rejection,
    UserSignals,
)


@dataclass(frozen=True)
class EligibilityInput:
    context: RecommendationContext
    signals: UserSignals
    as_of: date  # injected: the core never reads the clock

    @property
    def favorite_ids(self) -> frozenset[int]:
        return frozenset(f.title_id for f in self.signals.favorites)

    @property
    def watched_or_rated_ids(self) -> frozenset[int]:
        watched = {t.title_id for t in self.signals.watched}
        return frozenset(watched | {r.title_id for r in self.signals.ratings})

    @property
    def not_for_me_ids(self) -> frozenset[int]:
        return frozenset(t.title_id for t in self.signals.not_for_me)


Rule = Callable[[Candidate, EligibilityInput], Rejection | None]


def pool_status(c: Candidate, i: EligibilityInput) -> Rejection | None:
    """Defence in depth: retrieval should only return candidate-pool titles."""
    if c.adult or c.detail_level != "full" or c.provider_status != "active":
        return Rejection(c.title_id, "pool_status", "not a recommendable pool title")
    return None


def media_type(c: Candidate, i: EligibilityInput) -> Rejection | None:
    wanted = i.context.media_type
    if wanted != "any" and c.media_type != wanted:
        return Rejection(c.title_id, "media_type", f"is {c.media_type}, asked for {wanted}")
    return None


def context_genres(c: Candidate, i: EligibilityInput) -> Rejection | None:
    if i.context.genre_ids and not (c.genre_ids & i.context.genre_ids):
        return Rejection(c.title_id, "context_genres", "has none of the requested genres")
    return None


def max_runtime(c: Candidate, i: EligibilityInput) -> Rejection | None:
    """Movies only: TV runtimes are unreliable (R4). Unknown runtime fails a limit."""
    limit = i.context.max_runtime_minutes
    if limit is None or c.media_type != "movie":
        return None
    if c.runtime_minutes is None:
        return Rejection(c.title_id, "max_runtime", "runtime unknown")
    if c.runtime_minutes > limit:
        return Rejection(c.title_id, "max_runtime", f"{c.runtime_minutes} min > {limit}")
    return None


def avoided_genre(c: Candidate, i: EligibilityInput) -> Rejection | None:
    if c.genre_ids & i.signals.avoided_genre_ids:
        return Rejection(c.title_id, "avoided_genre", "has a genre the user avoids")
    return None


def favorite(c: Candidate, i: EligibilityInput) -> Rejection | None:
    if c.title_id in i.favorite_ids:
        return Rejection(c.title_id, "favorite", "already a favorite")
    return None


def watched_or_rated(c: Candidate, i: EligibilityInput) -> Rejection | None:
    """Already seen. ("Revisit watched titles" is a deferred context option.)"""
    if c.title_id in i.watched_or_rated_ids:
        return Rejection(c.title_id, "watched_or_rated", "already watched or rated")
    return None


def not_for_me(c: Candidate, i: EligibilityInput) -> Rejection | None:
    if c.title_id in i.not_for_me_ids:
        return Rejection(c.title_id, "not_for_me", "marked not for me")
    return None


def explicit_exclusion(c: Candidate, i: EligibilityInput) -> Rejection | None:
    if c.title_id in i.context.exclude_title_ids:
        return Rejection(c.title_id, "explicit_exclusion", "skipped or already shown")
    return None


def unreleased(c: Candidate, i: EligibilityInput) -> Rejection | None:
    if c.release_date is None or c.release_date > i.as_of:
        return Rejection(c.title_id, "unreleased", "no release date yet, or in the future")
    return None


ELIGIBILITY_RULES: tuple[Rule, ...] = (
    pool_status,
    media_type,
    context_genres,
    max_runtime,
    avoided_genre,
    favorite,
    watched_or_rated,
    not_for_me,
    explicit_exclusion,
    unreleased,
)


def check(
    candidates: Iterable[Candidate], given: EligibilityInput
) -> tuple[list[Candidate], list[Rejection]]:
    """Split candidates into (eligible, rejected), both sorted by title id."""
    eligible: list[Candidate] = []
    rejected: list[Rejection] = []
    for candidate in sorted(candidates, key=lambda c: c.title_id):
        rejection = next(
            (r for rule in ELIGIBILITY_RULES if (r := rule(candidate, given)) is not None), None
        )
        if rejection is None:
            eligible.append(candidate)
        else:
            rejected.append(rejection)
    return eligible, rejected
