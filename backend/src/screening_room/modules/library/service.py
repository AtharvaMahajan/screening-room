"""Library use cases: the user-title state rules (data-model.md §5).

Each function stages its changes; the handler commits once (ADR-0006), so a
rule that touches two tables (e.g. watched -> off the watchlist) is atomic.
`rec_result_id` records the recommendation an action came from (M4c).
"""

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import delete, exists, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from screening_room.core.errors import AppError
from screening_room.modules.catalog import service as catalog
from screening_room.modules.library.models import (
    Rating,
    TitleFeedback,
    ViewingEvent,
    WatchlistItem,
)
from screening_room.modules.library.schemas import (
    LibrarySignals,
    RatedTitleRef,
    TitleStateOut,
)

NOT_FOR_ME = "not_for_me"


def require_title(session: Session, title_id: int) -> None:
    """Any catalog title can be saved, watched or rated, not just pool titles."""
    if not catalog.title_exists(session, title_id):
        raise AppError(404, "title_not_found", "There's no such title.")


def title_state(session: Session, user_id: int, title_id: int) -> TitleStateOut:
    """The user's library state for one title, in a single query."""
    my_viewings = (ViewingEvent.user_id == user_id, ViewingEvent.title_id == title_id)
    row = session.execute(
        select(
            exists()
            .where(WatchlistItem.user_id == user_id, WatchlistItem.title_id == title_id)
            .label("in_watchlist"),
            select(func.count()).where(*my_viewings).scalar_subquery().label("watch_count"),
            select(func.max(ViewingEvent.watched_on))
            .where(*my_viewings)
            .scalar_subquery()
            .label("last_watched_on"),
            select(Rating.value)
            .where(Rating.user_id == user_id, Rating.title_id == title_id)
            .scalar_subquery()
            .label("rating"),
            exists()
            .where(
                TitleFeedback.user_id == user_id,
                TitleFeedback.title_id == title_id,
                TitleFeedback.kind == NOT_FOR_ME,
            )
            .label("not_for_me"),
        )
    ).one()
    return TitleStateOut(title_id=title_id, **row._asdict())


# --- Watchlist ------------------------------------------------------------------------------


def add_to_watchlist(
    session: Session, user_id: int, title_id: int, *, rec_result_id: int | None = None
) -> None:
    """Save for later. Saving again changes nothing (the first save is kept)."""
    require_title(session, title_id)
    session.execute(
        insert(WatchlistItem)
        .values(user_id=user_id, title_id=title_id, rec_result_id=rec_result_id)
        .on_conflict_do_nothing()
    )


def remove_from_watchlist(session: Session, user_id: int, title_id: int) -> None:
    session.execute(
        delete(WatchlistItem).where(
            WatchlistItem.user_id == user_id, WatchlistItem.title_id == title_id
        )
    )


# --- Viewing history ------------------------------------------------------------------------


def mark_watched(
    session: Session,
    user_id: int,
    title_id: int,
    watched_on: date | None = None,
    *,
    rec_result_id: int | None = None,
) -> None:
    """Record a viewing (again = a rewatch) and take the title off the watchlist."""
    require_title(session, title_id)
    # A day of slack: where the user is, "today" may already be tomorrow in UTC.
    if watched_on is not None and watched_on > datetime.now(UTC).date() + timedelta(days=1):
        raise AppError(422, "watched_on_in_future", "The watch date can't be in the future.")
    session.add(
        ViewingEvent(
            user_id=user_id, title_id=title_id, watched_on=watched_on, rec_result_id=rec_result_id
        )
    )
    remove_from_watchlist(session, user_id, title_id)


def unmark_watched(session: Session, user_id: int, title_id: int) -> None:
    """Forget every viewing of this title. A rating, if any, stays (data-model.md §5)."""
    session.execute(
        delete(ViewingEvent).where(
            ViewingEvent.user_id == user_id, ViewingEvent.title_id == title_id
        )
    )


# --- Ratings --------------------------------------------------------------------------------


def rate(
    session: Session, user_id: int, title_id: int, value: int, *, rec_result_id: int | None = None
) -> None:
    """Set the user's rating. A rating means they've seen it, so rating a title
    with no viewings also marks it watched (which takes it off the watchlist)."""
    require_title(session, title_id)
    statement = insert(Rating).values(
        user_id=user_id, title_id=title_id, value=value, rec_result_id=rec_result_id
    )
    session.execute(
        statement.on_conflict_do_update(
            index_elements=[Rating.user_id, Rating.title_id],
            set_={"value": statement.excluded.value, "updated_at": func.now()},
        )
    )
    has_viewed = session.scalar(
        select(exists().where(ViewingEvent.user_id == user_id, ViewingEvent.title_id == title_id))
    )
    if not has_viewed:
        mark_watched(session, user_id, title_id, rec_result_id=rec_result_id)


def remove_rating(session: Session, user_id: int, title_id: int) -> None:
    """Delete the rating. Viewings stay: the user still watched it."""
    session.execute(delete(Rating).where(Rating.user_id == user_id, Rating.title_id == title_id))


# --- Not for me -----------------------------------------------------------------------------


def mark_not_for_me(
    session: Session, user_id: int, title_id: int, *, rec_result_id: int | None = None
) -> None:
    """Never recommend this title again (until undone); counts against its genres (M4b)."""
    require_title(session, title_id)
    session.execute(
        insert(TitleFeedback)
        .values(user_id=user_id, title_id=title_id, kind=NOT_FOR_ME, rec_result_id=rec_result_id)
        .on_conflict_do_nothing()
    )


def undo_not_for_me(session: Session, user_id: int, title_id: int) -> None:
    session.execute(
        delete(TitleFeedback).where(
            TitleFeedback.user_id == user_id,
            TitleFeedback.title_id == title_id,
            TitleFeedback.kind == NOT_FOR_ME,
        )
    )


# --- For the recommender (M4b) ---------------------------------------------------------------


def taste_signals(session: Session, user_id: int) -> LibrarySignals:
    """The user's library as plain values, for the recommender."""

    def title_ids(table: type[WatchlistItem | ViewingEvent | TitleFeedback]) -> frozenset[int]:
        return frozenset(
            session.scalars(select(table.title_id).where(table.user_id == user_id).distinct())
        )

    ratings = session.execute(
        select(Rating.title_id, Rating.value, Rating.updated_at)
        .where(Rating.user_id == user_id)
        .order_by(Rating.title_id)
    )
    return LibrarySignals(
        ratings=tuple(RatedTitleRef(t, value, at) for t, value, at in ratings),
        watched_title_ids=title_ids(ViewingEvent),
        watchlist_title_ids=title_ids(WatchlistItem),
        not_for_me_title_ids=title_ids(TitleFeedback),  # its only kind is not_for_me
    )
