"""Recommendation API models (recommendation-engine.md §3, §15)."""

from typing import Annotated, Literal

from pydantic import BaseModel, Field

from screening_room.modules.catalog.schemas import TitlePreviewOut

MAX_CONTEXT_GENRES = 3
MAX_EXCLUDED_TITLES = 100
MAX_RUNTIME_MINUTES = 600  # nothing in a "what to watch tonight" pick runs longer

TitleId = Annotated[int, Field(ge=1, le=2**63 - 1)]


class RecommendationRequestIn(BaseModel):
    """What the user asked for this time. Every field is optional."""

    media_type: Literal["movie", "tv", "any"] = "any"
    genre_ids: list[int] = Field(default_factory=list, max_length=MAX_CONTEXT_GENRES)
    max_runtime_minutes: int | None = Field(default=None, ge=1, le=MAX_RUNTIME_MINUTES)
    # Titles to leave out: skipped ones, and those already shown ("show me more").
    exclude_title_ids: list[TitleId] = Field(default_factory=list, max_length=MAX_EXCLUDED_TITLES)
    limit: int = Field(default=5, ge=3, le=5)


class ReasonOut(BaseModel):
    type: Literal[
        "favorite_neighbor",
        "genre_affinity",
        "context_genre",
        "runtime_fit",
        "well_rated",
        "pool_source",
    ]
    text: str  # rendered server-side: one source of truth (§9)
    anchor_title_id: int | None = None  # favorite_neighbor: the favorite it came from


class RecommendationOut(BaseModel):
    result_id: int  # M4 attaches the user's actions (save, rate...) to this
    rank: int
    title: TitlePreviewOut
    reasons: list[ReasonOut]


class NoticeOut(BaseModel):
    code: Literal["cold_start", "few_results"]
    text: str


class RecommendationsOut(BaseModel):
    request_id: int
    cold_start: bool
    notices: list[NoticeOut]
    results: list[RecommendationOut]  # best first; may be fewer than asked for (§10)
