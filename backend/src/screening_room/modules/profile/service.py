"""Profile use cases. Services never commit (project-structure.md §5.1).

Uses the catalog only through its public service and schemas (ADR-0001).
"""

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from screening_room.core.errors import AppError
from screening_room.modules.catalog import service as catalog
from screening_room.modules.profile.models import UserFavoriteTitle, UserGenrePreference
from screening_room.modules.profile.schemas import (
    MAX_FAVORITES,
    FavoritePick,
    FavoritesOut,
    PreferencesIn,
    PreferencesOut,
    TasteSignals,
)

# --- Genre preferences --------------------------------------------------------------------


def get_preferences(session: Session, user_id: int) -> PreferencesOut:
    rows = session.execute(
        select(UserGenrePreference.genre_id, UserGenrePreference.stance)
        .where(UserGenrePreference.user_id == user_id)
        .order_by(UserGenrePreference.genre_id)
    ).all()
    return PreferencesOut(
        liked_genre_ids=[genre_id for genre_id, stance in rows if stance == "like"],
        avoided_genre_ids=[genre_id for genre_id, stance in rows if stance == "avoid"],
    )


def replace_preferences(session: Session, user_id: int, body: PreferencesIn) -> PreferencesOut:
    """Replace the user's liked and avoided genres wholesale (FR-02: editable later)."""
    liked, avoided = set(body.liked_genre_ids), set(body.avoided_genre_ids)
    if liked & avoided:
        raise AppError(422, "genre_conflict", "A genre can't be both liked and avoided.")
    selectable = {genre.id for genre in catalog.selectable_genres(session)}
    if unknown := (liked | avoided) - selectable:
        raise AppError(422, "unknown_genre", f"Unknown genre ids: {sorted(unknown)}.")

    session.execute(delete(UserGenrePreference).where(UserGenrePreference.user_id == user_id))
    session.add_all(
        UserGenrePreference(user_id=user_id, genre_id=genre_id, stance=stance)
        for stance, genre_ids in (("like", liked), ("avoid", avoided))
        for genre_id in sorted(genre_ids)
    )
    session.flush()
    return get_preferences(session, user_id)


# --- Favorites ----------------------------------------------------------------------------


def list_favorites(session: Session, user_id: int, image_base_url: str) -> FavoritesOut:
    title_ids = _favorite_ids(session, user_id)
    cards = catalog.title_cards(session, title_ids, image_base_url)
    return FavoritesOut(favorites=[cards[title_id] for title_id in title_ids if title_id in cards])


def add_favorite(session: Session, user_id: int, title_id: int) -> bool:
    """Add a favorite; True if it was new. Adding one twice changes nothing.

    Any catalog title can be a favorite, including ones found through TMDB
    search that aren't in the candidate pool (M4). The handler then fetches
    their full details, so their recommendation lists can anchor.
    """
    if title_id in _favorite_ids(session, user_id):
        return False
    if not catalog.title_exists(session, title_id):
        raise AppError(404, "title_not_found", "There's no such title to pick.")
    count = session.scalar(
        select(func.count())
        .select_from(UserFavoriteTitle)
        .where(UserFavoriteTitle.user_id == user_id)
    )
    # Enforced here, not in the schema: a count limit isn't practical as a DB
    # constraint (data-model.md §3.3). Two simultaneous adds by one user could
    # exceed it by one; accepted for a single person clicking.
    if (count or 0) >= MAX_FAVORITES:
        raise AppError(409, "favorites_limit", f"You can pick up to {MAX_FAVORITES} favorites.")
    session.execute(
        insert(UserFavoriteTitle)
        .values(user_id=user_id, title_id=title_id)
        .on_conflict_do_nothing()
    )
    return True


def remove_favorite(session: Session, user_id: int, title_id: int) -> None:
    """Remove a favorite. Removing one that isn't there is fine (idempotent)."""
    session.execute(
        delete(UserFavoriteTitle).where(
            UserFavoriteTitle.user_id == user_id, UserFavoriteTitle.title_id == title_id
        )
    )


def _favorite_ids(session: Session, user_id: int) -> list[int]:
    return list(
        session.scalars(
            select(UserFavoriteTitle.title_id)
            .where(UserFavoriteTitle.user_id == user_id)
            .order_by(UserFavoriteTitle.created_at, UserFavoriteTitle.title_id)
        )
    )


# --- For the recommender (M3c) -------------------------------------------------------------


def taste_signals(session: Session, user_id: int) -> TasteSignals:
    preferences = get_preferences(session, user_id)
    picks = session.execute(
        select(UserFavoriteTitle.title_id, UserFavoriteTitle.created_at)
        .where(UserFavoriteTitle.user_id == user_id)
        .order_by(UserFavoriteTitle.created_at, UserFavoriteTitle.title_id)
    )
    return TasteSignals(
        liked_genre_ids=frozenset(preferences.liked_genre_ids),
        avoided_genre_ids=frozenset(preferences.avoided_genre_ids),
        favorite_picks=tuple(FavoritePick(title_id, picked_at) for title_id, picked_at in picks),
    )
