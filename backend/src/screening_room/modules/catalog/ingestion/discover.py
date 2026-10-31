"""Phase 1, discover: page through each seed source and record what's in the pool
(catalog-ingestion.md §6).

Each page is fetched with no database connection checked out, then written in
one short transaction: summary rows plus "this source returned this title".
"""

import logging
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy.orm import Session, sessionmaker

from screening_room.modules.catalog import service
from screening_room.modules.catalog.ingestion.seed_plan import SeedSource
from screening_room.modules.catalog.providers.base import CatalogProvider

logger = logging.getLogger(__name__)


@dataclass
class DiscoverCounts:
    discovered: int = 0  # list results seen (a title in 5 sources counts 5 times)
    inserted: int = 0  # titles new to the catalog
    updated: int = 0  # titles we already had
    pool_added: int = 0  # titles new to the pool
    skipped_by_cap: int = 0  # new titles left out because of --max-titles
    sources: list[str] = field(default_factory=list)


def discover(
    session_factory: sessionmaker[Session],
    provider: CatalogProvider,
    sources: Iterable[SeedSource],
    run_id: int,
    max_titles: int,
    counts: DiscoverCounts | None = None,
) -> DiscoverCounts:
    # The caller may pass its own counts, so they survive an interrupted run.
    counts = counts if counts is not None else DiscoverCounts()
    with session_factory() as session:
        pool_size = service.count_pool_titles(session)

    for source in sources:
        rank = 0  # position in this source's results, across pages
        for page_number in range(1, source.pages + 1):
            page = provider.list_titles(source.query, page_number)  # no connection held

            with session_factory() as session:
                now = datetime.now(UTC)
                known = service.title_ids_for_refs(session, (s.ref for s in page.results))
                pooled = service.pool_title_ids(session, known.values())
                for summary in page.results:
                    rank += 1
                    if summary.adult:
                        continue  # never stored or pooled (R18)
                    existing_id = known.get(summary.ref)
                    in_pool = existing_id in pooled
                    if not in_pool and pool_size >= max_titles:
                        counts.skipped_by_cap += 1
                        continue
                    title_id = service.upsert_title_summary(session, summary, now)
                    service.upsert_pool_membership(session, title_id, source.key, rank, run_id)
                    counts.discovered += 1
                    if existing_id is None:
                        counts.inserted += 1
                    else:
                        counts.updated += 1
                    if not in_pool:
                        pool_size += 1
                        counts.pool_added += 1
                session.commit()

            if page_number >= page.total_pages:
                break  # the source has fewer pages than its quota
        counts.sources.append(source.key)
        logger.info("discover %-40s pool size %d", source.key, pool_size)
    return counts
