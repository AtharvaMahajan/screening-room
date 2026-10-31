"""The engine's inputs and outputs (recommendation-engine.md §2-3).

All frozen dataclasses of plain values: the service builds them from the
database (M3c); the engine never sees ORM objects or a Session.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Literal

MediaType = Literal["movie", "tv"]
ContextMediaType = Literal["movie", "tv", "any"]

# --- Inputs ----------------------------------------------------------------------------


@dataclass(frozen=True)
class RecommendationContext:
    """What the user asked for this time. Validated by the API (M3c)."""

    media_type: ContextMediaType = "any"
    genre_ids: frozenset[int] = frozenset()  # at most 3
    max_runtime_minutes: int | None = None  # movies only (R4)
    exclude_title_ids: frozenset[int] = frozenset()  # skipped / "show me more"
    limit: int = 5  # 3-5


@dataclass(frozen=True)
class Favorite:
    title_id: int
    name: str  # for "Because you picked {name}"
    genre_ids: frozenset[int]
    picked_at: datetime  # newer favorites win anchor ties


@dataclass(frozen=True)
class UserSignals:
    """M3: onboarding preferences. M4 adds ratings, watched, watchlist, not_for_me."""

    liked_genre_ids: frozenset[int] = frozenset()
    avoided_genre_ids: frozenset[int] = frozenset()
    favorites: tuple[Favorite, ...] = ()


@dataclass(frozen=True)
class Candidate:
    """A candidate-pool title's features (retrieval, M3c)."""

    title_id: int
    media_type: MediaType
    genre_ids: frozenset[int]
    runtime_minutes: int | None
    release_date: date | None
    vote_average: float | None
    vote_count: int | None
    popularity: float | None
    source_keys: frozenset[str]  # why it's in the pool, e.g. "movie:top_rated"
    # Re-checked by eligibility even though retrieval already filters on them.
    detail_level: str = "full"
    provider_status: str = "active"
    adult: bool = False


@dataclass(frozen=True)
class PoolStats:
    mean_vote_average: float  # C in the Bayesian average
    max_popularity: float
    pool_size: int


@dataclass(frozen=True)
class Neighbor:
    """An anchor's TMDB recommendation, already resolved to a pool title (retrieval)."""

    title_id: int
    provider_rank: int  # 1 = TMDB's first recommendation


# Anchor title id -> its neighbors (only those in the candidate pool).
NeighborIndex = Mapping[int, tuple[Neighbor, ...]]


# --- Intermediate values ---------------------------------------------------------------


@dataclass(frozen=True)
class Anchor:
    title_id: int
    name: str
    kind: Literal["favorite"]  # M4 adds rated titles
    weight: float


@dataclass(frozen=True)
class TasteProfile:
    genre_weights: Mapping[int, float]  # signed; avoided genres aren't here (hard rule)
    anchors: tuple[Anchor, ...]  # best first, capped

    @property
    def is_empty(self) -> bool:
        return not any(self.genre_weights.values()) and not self.anchors


@dataclass(frozen=True)
class NeighborSource:
    """Which anchor gave a candidate its favorite_neighbor value."""

    anchor_title_id: int
    anchor_name: str
    anchor_kind: str
    provider_rank: int
    provider: str = "tmdb"


@dataclass(frozen=True)
class SignalScore:
    value: float  # the signal itself, e.g. affinity in [-1, 1]
    weighted: float  # value x its weight: its contribution to the score


@dataclass(frozen=True)
class ScoreBreakdown:
    affinity: SignalScore
    favorite_neighbor: SignalScore
    quality: SignalScore
    popularity: SignalScore
    neighbor_source: NeighborSource | None

    @property
    def total(self) -> float:
        return (
            self.affinity.weighted
            + self.favorite_neighbor.weighted
            + self.quality.weighted
            + self.popularity.weighted
        )


@dataclass(frozen=True)
class ScoredCandidate:
    candidate: Candidate
    breakdown: ScoreBreakdown

    @property
    def score(self) -> float:
        return self.breakdown.total


# --- Outputs ---------------------------------------------------------------------------

ReasonType = Literal[
    "favorite_neighbor",
    "genre_affinity",
    "context_genre",
    "runtime_fit",
    "well_rated",
    "pool_source",
]
PERSONAL_REASONS: frozenset[str] = frozenset({"favorite_neighbor", "genre_affinity"})


@dataclass(frozen=True)
class Reason:
    type: ReasonType
    text: str  # rendered here, so there's one source of truth (§9)
    params: Mapping[str, int | str] = field(default_factory=dict)


@dataclass(frozen=True)
class Result:
    rank: int  # 1-based
    title_id: int
    score: float
    breakdown: ScoreBreakdown
    reasons: tuple[Reason, ...]


@dataclass(frozen=True)
class Rejection:
    """Why a candidate was ineligible: answers "why wasn't X recommended?"."""

    title_id: int
    rule: str
    detail: str


@dataclass(frozen=True)
class Notice:
    code: str
    text: str


@dataclass(frozen=True)
class Diagnostics:
    candidate_count: int
    eligible_count: int
    anchor_count: int
    anchors_without_neighbors: int  # anchors with no eligible neighbor (§7.1)


@dataclass(frozen=True)
class RecommendationOutcome:
    results: tuple[Result, ...]
    rejected: tuple[Rejection, ...]
    cold_start: bool
    diversity_relaxed: bool
    notices: tuple[Notice, ...]
    diagnostics: Diagnostics
