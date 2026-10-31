"""Library API models (data-model.md §3.5, §5)."""

from dataclasses import dataclass
from datetime import date, datetime

from pydantic import BaseModel, Field

from screening_room.modules.catalog.schemas import TitleCardOut


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


# --- Library lists (M4d, FR-12) -----------------------------------------------------------


class WatchlistItemOut(BaseModel):
    title: TitleCardOut
    added_at: datetime


class ViewingOut(BaseModel):
    """One viewing: a rewatch is its own entry."""

    id: int
    title: TitleCardOut
    watched_on: date | None  # when the user said they watched it, if they did
    created_at: datetime  # when it was recorded


class RatingOut(BaseModel):
    title: TitleCardOut
    value: int
    rated_at: datetime  # last changed


class NotForMeOut(BaseModel):
    title: TitleCardOut
    marked_at: datetime


# --- For the recommender (M4b) ---------------------------------------------------------------


@dataclass(frozen=True)
class RatedTitleRef:
    title_id: int
    stars: int
    rated_at: datetime  # last set: newer ratings win anchor ties


@dataclass(frozen=True)
class LibrarySignals:
    """What the recommender needs from the library (recommendation-engine.md §4, §6)."""

    ratings: tuple[RatedTitleRef, ...]  # by title id
    watched_title_ids: frozenset[int]
    watchlist_title_ids: frozenset[int]
    not_for_me_title_ids: frozenset[int]

    @property
    def title_ids(self) -> frozenset[int]:
        """Every title mentioned: retrieval looks up their names and genres."""
        rated = {r.title_id for r in self.ratings}
        return frozenset(
            rated | self.watched_title_ids | self.watchlist_title_ids | self.not_for_me_title_ids
        )
