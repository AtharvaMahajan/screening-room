"""Library API models (data-model.md §3.5, §5)."""

from datetime import date

from pydantic import BaseModel, Field


class TitleStateOut(BaseModel):
    """Everything the signed-in user has recorded about one title (ADR-0008).

    The states are independent: e.g. a title can be rated and "not for me".
    """

    title_id: int
    in_watchlist: bool
    watch_count: int  # viewings recorded; more than 1 means rewatches
    last_watched_on: date | None  # the latest date given, if any was
    rating: int | None  # 1-5 stars
    not_for_me: bool


class ViewingIn(BaseModel):
    watched_on: date | None = None  # optional: "I've seen it" is enough


class RatingIn(BaseModel):
    value: int = Field(ge=1, le=5)  # whole stars (ADR-0009)
