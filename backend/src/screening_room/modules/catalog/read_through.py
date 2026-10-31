"""Title detail with read-through (catalog-ingestion.md §11, overview.md §6.2).

A handler-level helper: one of the few places allowed to end transactions and
commit (project-structure.md §5.3). The sequence:

1. Load the title as plain values in the request's transaction.
2. Fully hydrated and fresh: return it. Nothing is written, nothing to commit.
3. Otherwise end the read transaction FIRST, so no transaction or pooled
   connection is held while waiting on TMDB (ADR-0006), then fetch.
4. Success: hydrate in one short write transaction, commit, reload, "fresh".
5. Failure: record it in a short transaction and return what we have, marked
   "stale" (full but old) or "partial" (summary only). A detail page never
   fails just because TMDB is down.
"""

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from screening_room.config import CatalogSettings
from screening_room.core.errors import AppError
from screening_room.db import end_read_transaction
from screening_room.modules.catalog import service
from screening_room.modules.catalog.providers.base import (
    CatalogProvider,
    ProviderError,
    ProviderNotFoundError,
)
from screening_room.modules.catalog.schemas import (
    CastMemberOut,
    GenreOut,
    MetadataStatus,
    TitleDetailOut,
    TitleRecord,
)
from screening_room.modules.catalog.service import (
    BACKDROP_SIZE,
    POSTER_SIZE,
    PROFILE_SIZE,
    image_url,
)

logger = logging.getLogger(__name__)


def get_title_detail(
    session: Session,
    title_id: int,
    provider: CatalogProvider | None,
    settings: CatalogSettings,
) -> TitleDetailOut:
    now = datetime.now(UTC)
    record = service.load_title_record(session, title_id)
    if record is None or record.adult:  # adult titles are never shown (R18)
        raise AppError(404, "title_not_found", "There's no such title.")

    stale_before = now - timedelta(days=settings.catalog_ttl_days)
    if (
        record.detail_level == "full"
        and record.details_synced_at
        and record.details_synced_at >= stale_before
    ):
        return _to_out(record, "fresh", settings)

    # Release the transaction and its connection before any network call.
    end_read_transaction(session)
    if provider is None:  # no TMDB token configured: serve what we have
        return _to_out(record, _fallback_status(record), settings)

    try:
        details = provider.get_details(record.ref)
    except ProviderNotFoundError:
        service.mark_title_missing(session, title_id)
        session.commit()
        return _to_out(record, _fallback_status(record), settings)
    except ProviderError as error:  # timeouts, outages, bad credentials...
        logger.warning("read-through for title %d failed: %s", title_id, error)
        service.record_sync_error(session, title_id, str(error), now)
        session.commit()
        return _to_out(record, _fallback_status(record), settings)

    try:
        genre_map = service.load_genre_map(session, provider.name)
        service.apply_title_details(session, title_id, details, genre_map, None, now)
    except service.UnmappedGenreError as error:
        # Don't fail the page; record it so ingestion surfaces it loudly.
        session.rollback()
        logger.error("read-through for title %d: %s", title_id, error)
        service.record_sync_error(session, title_id, str(error), now)
        session.commit()
        return _to_out(record, _fallback_status(record), settings)
    session.commit()

    refreshed = service.load_title_record(session, title_id)
    assert refreshed is not None
    return _to_out(refreshed, "fresh", settings)


def _fallback_status(record: TitleRecord) -> MetadataStatus:
    return "stale" if record.detail_level == "full" else "partial"


def _to_out(
    record: TitleRecord, status: MetadataStatus, settings: CatalogSettings
) -> TitleDetailOut:
    return TitleDetailOut(
        id=record.id,
        media_type=record.ref.media_type,
        name=record.name,
        original_name=record.original_name,
        overview=record.overview,
        release_date=record.release_date,
        runtime_minutes=record.runtime_minutes,
        number_of_seasons=record.number_of_seasons,
        original_language=record.original_language,
        vote_average=record.vote_average,
        vote_count=record.vote_count,
        poster_url=image_url(settings.tmdb_image_base_url, POSTER_SIZE, record.poster_path),
        backdrop_url=image_url(settings.tmdb_image_base_url, BACKDROP_SIZE, record.backdrop_path),
        genres=[
            GenreOut(id=genre_id, slug=slug, name=name) for genre_id, slug, name in record.genres
        ],
        cast=[
            CastMemberOut(
                name=member.name,
                character=member.character,
                profile_url=image_url(
                    settings.tmdb_image_base_url, PROFILE_SIZE, member.profile_path
                ),
            )
            for member in record.cast
        ],
        directors=list(record.directors),
        creators=list(record.creators),
        metadata_status=status,
    )
