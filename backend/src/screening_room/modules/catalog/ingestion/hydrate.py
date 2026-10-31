"""Phase 2, hydrate: fetch details, credits and recommendation lists for pool titles
that are summary-only or stale (catalog-ingestion.md §7, §10).

Worker threads only talk to the provider. The main thread takes their results
in submission order and writes each title in its own short transaction,
committed before it waits for the next result. A Session isn't thread-safe,
so no worker ever touches the database.
"""

import logging
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import Session, sessionmaker

from screening_room.modules.catalog import service
from screening_room.modules.catalog.providers.base import (
    CatalogProvider,
    ProviderAuthError,
    ProviderError,
    ProviderNotFoundError,
    ProviderRef,
    TitleDetails,
)

logger = logging.getLogger(__name__)
PROGRESS_EVERY = 100


@dataclass
class HydrateCounts:
    selected: int = 0
    hydrated: int = 0
    missing: int = 0  # provider answered 404
    failed: int = 0  # other errors, recorded on the title; retried next run


def hydrate(
    session_factory: sessionmaker[Session],
    provider: CatalogProvider,
    genre_map: service.GenreMap,
    run_id: int,
    *,
    stale_before: datetime,
    include_summary_only: bool,
    limit: int | None,
    max_workers: int,
    counts: HydrateCounts | None = None,
) -> HydrateCounts:
    # The caller may pass its own counts, so they survive an interrupted run.
    counts = counts if counts is not None else HydrateCounts()
    # Read the work list as plain values, then release the connection.
    with session_factory() as session:
        todo = service.titles_to_hydrate(
            session,
            stale_before=stale_before,
            include_summary_only=include_summary_only,
            limit=limit,
        )
    counts.selected = len(todo)
    logger.info("hydrate: %d titles to fetch", len(todo))

    executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="hydrate")
    try:
        jobs: list[tuple[int, ProviderRef, Future[TitleDetails]]] = [
            (title_id, ref, executor.submit(provider.get_details, ref)) for title_id, ref in todo
        ]
        for done, (title_id, ref, future) in enumerate(jobs, start=1):
            _store(session_factory, title_id, ref, future, genre_map, run_id, counts)
            if done % PROGRESS_EVERY == 0:
                logger.info("hydrate: %d of %d done", done, len(jobs))
    finally:
        # If anything aborted the run, don't keep fetching titles nobody will store.
        executor.shutdown(wait=True, cancel_futures=True)
    return counts


def _store(
    session_factory: sessionmaker[Session],
    title_id: int,
    ref: ProviderRef,
    future: Future[TitleDetails],
    genre_map: service.GenreMap,
    run_id: int,
    counts: HydrateCounts,
) -> None:
    """Wait for one fetch, then write its outcome in one short transaction."""
    try:
        details = future.result()  # waiting here: no session is open
    except ProviderAuthError:
        raise  # bad credentials: every other request will fail too
    except ProviderNotFoundError:
        with session_factory() as session:
            service.mark_title_missing(session, title_id)
            session.commit()
        counts.missing += 1
        return
    except ProviderError as error:
        with session_factory() as session:
            service.record_sync_error(session, title_id, str(error), datetime.now(UTC))
            session.commit()
        counts.failed += 1
        logger.warning("hydrate: %s failed: %s", ref, error)
        return

    with session_factory() as session:
        service.apply_title_details(
            session, title_id, details, genre_map, run_id, datetime.now(UTC)
        )
        session.commit()
    counts.hydrated += 1
