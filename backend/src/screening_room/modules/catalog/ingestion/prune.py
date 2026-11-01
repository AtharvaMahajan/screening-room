"""Prune: remove old TMDB data nobody uses (API Terms of Use §1.C: cache at most 6 months).

Titles outside the candidate pool arrive through search and title pages. Once
their data is older than `older_than`, they're deleted, unless users still
reference them (favorites, library, recommendation logs). The catalog module
can't look at those tables (ADR-0001), and doesn't need to: their foreign keys
are RESTRICT, so the database refuses the delete and the title is kept. Kept
titles are then kept fresh by `refresh`, which covers every stored title.

Local only: no TMDB requests. Run it before `refresh`.
"""

import logging
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from screening_room.modules.catalog import service

logger = logging.getLogger(__name__)


@dataclass
class PruneCounts:
    candidates: int = 0  # outside the pool and older than the cutoff
    deleted: int = 0
    kept_in_use: int = 0  # referenced by user data: refreshed instead


def prune_outside_pool(
    session_factory: sessionmaker[Session], *, older_than: datetime
) -> PruneCounts:
    counts = PruneCounts()
    with session_factory() as session:
        title_ids = service.stale_titles_outside_pool(session, older_than)
        counts.candidates = len(title_ids)
        for title_id in title_ids:
            try:
                with session.begin_nested():  # a savepoint: one refusal doesn't undo the rest
                    service.delete_title(session, title_id)
                counts.deleted += 1
            except IntegrityError:
                counts.kept_in_use += 1
        session.commit()
    logger.info(
        "prune: %d deleted, %d kept (in use)",
        counts.deleted,
        counts.kept_in_use,
        extra={"fields": {"deleted": counts.deleted, "kept_in_use": counts.kept_in_use}},
    )
    return counts
