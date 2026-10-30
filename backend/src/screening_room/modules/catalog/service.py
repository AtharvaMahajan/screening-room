"""Catalog use cases and queries.

Services never commit (project-structure.md §5.1). Later milestones add title
detail (M2) and pool retrieval (M3) here.
"""

from sqlalchemy import ColumnElement, and_, exists

from screening_room.modules.catalog.models import CandidatePoolMembership, Title


def in_candidate_pool() -> ColumnElement[bool]:
    """SQL condition: this `Title` may be recommended (data-model.md §4).

    The catalog holds everything we know about, including titles that only came
    from a detail view or a search. Only these can be recommended:
    - a seed source put it in the pool (at least one membership),
    - it has been fully hydrated (details, genres, credits),
    - the provider still has it, and
    - it isn't adult content.

    For the catalog module's own queries. Other modules use catalog query
    functions built on this, never their own joins (ADR-0001).
    """
    return and_(
        exists().where(CandidatePoolMembership.title_id == Title.id),
        Title.detail_level == "full",
        Title.provider_status == "active",
        Title.adult.is_(False),
    )
