"""Command-line jobs (ADR-0005, catalog-ingestion.md §3). Run from backend/:

    uv run python -m screening_room.jobs ingest [--plan starter-v1] [--media movie|tv|all]
                                                [--max-titles 2000] [--max-requests N] [--dry-run]
    uv run python -m screening_room.jobs refresh [--older-than-days 14] [--limit N]
                                                 [--max-requests N]
    uv run python -m screening_room.jobs report
    uv run python -m screening_room.jobs prune [--older-than-days 30]
    uv run python -m screening_room.jobs metrics [--days 7]

This module only parses arguments and wires up real dependencies; the work is
in modules/catalog/ingestion/, where tests run it against a FakeProvider.
"""

import argparse
import sys
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from screening_room.config import JobSettings, LogSettings
from screening_room.core.logging import configure_logging
from screening_room.db import create_db_engine, create_session_factory
from screening_room.modules.catalog.ingestion.prune import prune_outside_pool
from screening_room.modules.catalog.ingestion.report import build_report
from screening_room.modules.catalog.ingestion.runs import (
    IngestOptions,
    RefreshOptions,
    RunResult,
    plan_sources,
    run_ingest,
    run_refresh,
)
from screening_room.modules.catalog.ingestion.seed_plan import PLANS, SEED_PLAN_VERSION
from screening_room.modules.catalog.providers.tmdb.client import TmdbClient
from screening_room.modules.catalog.providers.tmdb.provider import TmdbProvider
from screening_room.modules.discovery.metrics import format_report, recommendation_metrics


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m screening_room.jobs")
    commands = parser.add_subparsers(dest="command", required=True)

    ingest = commands.add_parser("ingest", help="discover seed sources, then hydrate the pool")
    ingest.add_argument("--plan", choices=sorted(PLANS), default=SEED_PLAN_VERSION)
    ingest.add_argument("--media", choices=["movie", "tv", "all"], default="all")
    ingest.add_argument("--max-titles", type=int, default=2000, help="cap on pool size")
    ingest.add_argument("--max-requests", type=int, help="hard budget of provider requests")
    ingest.add_argument(
        "--dry-run", action="store_true", help="show the plan; no requests or writes"
    )

    refresh = commands.add_parser("refresh", help="re-hydrate stale pool titles")
    refresh.add_argument("--older-than-days", type=int, help="default: CATALOG_TTL_DAYS")
    refresh.add_argument("--limit", type=int)
    refresh.add_argument("--max-requests", type=int)

    commands.add_parser("report", help="pool composition and health (no provider calls)")

    prune = commands.add_parser(
        "prune", help="delete old titles outside the pool that nobody uses (no provider calls)"
    )
    prune.add_argument("--older-than-days", type=int, default=30)

    metrics = commands.add_parser(
        "metrics", help="recommendation latency, coverage and outcomes (no provider calls)"
    )
    metrics.add_argument("--days", type=int, default=7, help="window, ending now")
    return parser


def describe_plan(options: IngestOptions) -> str:
    sources = plan_sources(options)
    lines = [f"Seed plan {options.plan} ({options.media}): {len(sources)} sources"]
    lines += [f"  {s.key:<45} {s.pages} page(s)" for s in sources]
    list_requests = sum(s.pages for s in sources)
    lines += [
        "",
        f"Discover: up to {list_requests} list requests (fewer if a source runs out of pages)",
        "Genre check: 1 request per media type",
        f"Hydrate: 1 request per new or stale pool title, at most {options.max_titles} "
        "(the pool cap)",
    ]
    if options.max_requests:
        lines.append(f"Budget: stops after {options.max_requests} requests in total")
    return "\n".join(lines)


def print_result(result: RunResult) -> None:
    counts = ", ".join(f"{k}={v}" for k, v in sorted(result.counts.items()))
    print(f"Run #{result.run_id}: {result.status}\n  {counts}")
    if result.error_summary:
        print(f"  {result.error_summary}")


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    log_settings = LogSettings()
    configure_logging(log_settings.log_format, log_settings.log_level)

    if args.command == "ingest" and args.dry_run:
        options = IngestOptions(args.plan, args.media, args.max_titles, args.max_requests)
        print(describe_plan(options))
        return 0

    settings = JobSettings()
    engine = create_db_engine(settings.database_url)
    session_factory = create_session_factory(engine)
    try:
        if args.command == "prune":
            older_than = datetime.now(UTC) - timedelta(days=args.older_than_days)
            counts = prune_outside_pool(session_factory, older_than=older_than)
            print(f"Pruned {counts.deleted} titles; kept {counts.kept_in_use} still in use.")
            return 0
        if args.command == "metrics":
            since = datetime.now(UTC) - timedelta(days=args.days)
            with session_factory() as session:
                print(format_report(recommendation_metrics(session, since)))
            return 0
        if args.command == "report":
            with session_factory() as session:
                print(
                    build_report(session, now=datetime.now(UTC), ttl_days=settings.catalog_ttl_days)
                )
            return 0

        client = TmdbClient(
            settings.require_tmdb_token(), rate_limit_rps=settings.tmdb_rate_limit_rps
        )
        try:
            provider = TmdbProvider(client)
            if args.command == "ingest":
                options = IngestOptions(args.plan, args.media, args.max_titles, args.max_requests)
                result = run_ingest(
                    session_factory,
                    provider,
                    options,
                    ttl_days=settings.catalog_ttl_days,
                    max_workers=settings.tmdb_max_workers,
                )
            else:
                refresh = RefreshOptions(
                    args.older_than_days or settings.catalog_ttl_days, args.limit, args.max_requests
                )
                result = run_refresh(
                    session_factory, provider, refresh, max_workers=settings.tmdb_max_workers
                )
        finally:
            client.close()
        print_result(result)
        return 1 if result.status == "failed" else 0
    finally:
        engine.dispose()


if __name__ == "__main__":
    sys.exit(main())
