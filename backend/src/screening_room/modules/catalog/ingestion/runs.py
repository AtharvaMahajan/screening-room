"""One `ingest` or `refresh` run, start to finish, recorded in ingestion_runs (ADR-0005).

Run status:
- succeeded: everything worked
- partial: some titles failed, or --max-requests stopped the run early;
  re-running continues where it left off
- failed: the run stopped (bad credentials, an unmapped genre, Ctrl+C, a bug)
"""

import logging
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from sqlalchemy.orm import Session, sessionmaker

from screening_room.modules.catalog import service
from screening_room.modules.catalog.ingestion.budget import BudgetExhaustedError, CountingProvider
from screening_room.modules.catalog.ingestion.discover import DiscoverCounts, discover
from screening_room.modules.catalog.ingestion.hydrate import HydrateCounts, hydrate
from screening_room.modules.catalog.ingestion.seed_plan import MEDIA_TYPES, PLANS, SeedSource
from screening_room.modules.catalog.models import IngestionRun
from screening_room.modules.catalog.providers.base import (
    CatalogProvider,
    MediaType,
    ProviderAuthError,
)

logger = logging.getLogger(__name__)

MediaOption = Literal["movie", "tv", "all"]
# The body of a run: does the work given the counting provider and the run id.
Work = Callable[[CountingProvider, int], None]


@dataclass(frozen=True)
class IngestOptions:
    plan: str = "starter-v1"
    media: MediaOption = "all"
    max_titles: int = 2000
    max_requests: int | None = None


@dataclass(frozen=True)
class RefreshOptions:
    older_than_days: int = 14
    limit: int | None = None
    max_requests: int | None = None


@dataclass
class RunResult:
    run_id: int
    status: str
    error_summary: str | None
    counts: dict[str, Any] = field(default_factory=dict)


def media_types(option: MediaOption) -> tuple[MediaType, ...]:
    return MEDIA_TYPES if option == "all" else (option,)


def plan_sources(options: IngestOptions) -> list[SeedSource]:
    wanted = media_types(options.media)
    return [source for source in PLANS[options.plan]() if source.query.media_type in wanted]


def run_ingest(
    session_factory: sessionmaker[Session],
    provider: CatalogProvider,
    options: IngestOptions,
    *,
    ttl_days: int,
    max_workers: int,
) -> RunResult:
    """Discover every seed source, then hydrate summary-only and stale pool titles."""
    found, hydrated = DiscoverCounts(), HydrateCounts()

    def work(counted: CountingProvider, run_id: int) -> None:
        genre_map = _checked_genre_map(session_factory, counted, media_types(options.media))
        discover(session_factory, counted, plan_sources(options), run_id, options.max_titles, found)
        hydrate(
            session_factory,
            counted,
            genre_map,
            run_id,
            stale_before=datetime.now(UTC) - timedelta(days=ttl_days),
            include_summary_only=True,
            limit=None,
            max_workers=max_workers,
            counts=hydrated,
        )

    return _run(
        session_factory,
        provider,
        "ingest",
        options.plan,
        asdict(options),
        options.max_requests,
        work,
        lambda: _counts(found, hydrated),
    )


def run_refresh(
    session_factory: sessionmaker[Session],
    provider: CatalogProvider,
    options: RefreshOptions,
    *,
    max_workers: int,
) -> RunResult:
    """Re-hydrate pool titles whose details are older than the TTL."""
    hydrated = HydrateCounts()

    def work(counted: CountingProvider, run_id: int) -> None:
        genre_map = _checked_genre_map(session_factory, counted, MEDIA_TYPES)
        hydrate(
            session_factory,
            counted,
            genre_map,
            run_id,
            stale_before=datetime.now(UTC) - timedelta(days=options.older_than_days),
            include_summary_only=False,
            limit=options.limit,
            max_workers=max_workers,
            counts=hydrated,
        )

    return _run(
        session_factory,
        provider,
        "refresh",
        None,
        asdict(options),
        options.max_requests,
        work,
        lambda: _counts(None, hydrated),
    )


def _run(
    session_factory: sessionmaker[Session],
    provider: CatalogProvider,
    command: str,
    plan_version: str | None,
    params: dict[str, Any],
    max_requests: int | None,
    work: Work,
    counts_so_far: Callable[[], dict[str, Any]],
) -> RunResult:
    """Open the run row, do the work, and always close the row with an honest status
    and whatever was counted, even if the run stopped early."""
    with session_factory() as session:
        run = IngestionRun(
            command=command,
            seed_plan_version=plan_version,
            params=params,
            status="running",
            counts={},
        )
        session.add(run)
        session.commit()
        run_id = run.id

    counted = CountingProvider(provider, max_requests)
    error: str | None = None
    try:
        work(counted, run_id)
        status = "partial" if counts_so_far().get("failed") else "succeeded"
    except BudgetExhaustedError as exc:
        status, error = "partial", f"Stopped early: {exc}. Run again to continue."
    except (ProviderAuthError, service.UnmappedGenreError) as exc:
        status, error = "failed", str(exc)
    except BaseException as exc:  # Ctrl+C or a bug: record it, then let it propagate
        _finish(
            session_factory,
            run_id,
            "failed",
            counts_so_far(),
            counted.requests,
            f"{type(exc).__name__}: {exc}",
        )
        raise
    counts = counts_so_far()
    _finish(session_factory, run_id, status, counts, counted.requests, error)
    return RunResult(run_id, status, error, counts | {"requests": counted.requests})


def _finish(
    session_factory: sessionmaker[Session],
    run_id: int,
    status: str,
    counts: dict[str, Any],
    requests: int,
    error: str | None,
) -> None:
    with session_factory() as session:
        run = session.get_one(IngestionRun, run_id)
        run.status = status
        run.counts = counts | {"requests": requests}
        run.finished_at = datetime.now(UTC)
        run.error_summary = error
        session.commit()
    logger.info(
        "run #%d %s (%d requests)%s", run_id, status, requests, f": {error}" if error else ""
    )


def _checked_genre_map(
    session_factory: sessionmaker[Session],
    provider: CatalogProvider,
    media: tuple[MediaType, ...],
) -> service.GenreMap:
    """Load our genre mapping and stop now if the provider has a genre it lacks."""
    with session_factory() as session:
        genre_map = service.load_genre_map(session, provider.name)
    for media_type in media:
        service.check_genres_mapped(genre_map, media_type, provider.list_genres(media_type))
    return genre_map


def _counts(found: DiscoverCounts | None, hydrated: HydrateCounts) -> dict[str, Any]:
    counts: dict[str, Any] = asdict(hydrated)
    if found is not None:
        counts |= {k: v for k, v in asdict(found).items() if k != "sources"}
        counts["sources"] = len(found.sources)
    return counts
