"""Profile DTOs: API models, and the taste signals the recommender reads (M3c)."""

from dataclasses import dataclass

from pydantic import BaseModel, Field

from screening_room.modules.catalog.schemas import TitleCardOut

MAX_FAVORITES = 10  # initial value (roadmap M3)


class PreferencesIn(BaseModel):
    """Replaces the user's genre preferences. A genre can't be both."""

    liked_genre_ids: list[int] = Field(default_factory=list, max_length=30)
    avoided_genre_ids: list[int] = Field(default_factory=list, max_length=30)


class PreferencesOut(BaseModel):
    liked_genre_ids: list[int]
    avoided_genre_ids: list[int]


class FavoriteIn(BaseModel):
    title_id: int = Field(ge=1, le=2**63 - 1)


class FavoritesOut(BaseModel):
    favorites: list[TitleCardOut]  # oldest first: the order they were picked
    max_favorites: int = MAX_FAVORITES


@dataclass(frozen=True)
class TasteSignals:
    """What the recommender needs from the profile (recommendation-engine.md §3)."""

    liked_genre_ids: frozenset[int]
    avoided_genre_ids: frozenset[int]
    favorite_title_ids: tuple[int, ...]  # oldest first
