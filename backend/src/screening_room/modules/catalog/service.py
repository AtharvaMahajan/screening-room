"""Catalog use cases and queries.

Services never commit (project-structure.md §5.1): ingestion jobs and, from M2d,
the read-through helper own the transactions. The write functions here are
shared by both, so a title is stored the same way whichever path fetched it.
"""

from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime
from typing import Any, cast

from sqlalchemy import ColumnElement, and_, delete, exists, func, or_, select, tuple_, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from screening_room.modules.catalog.models import (
    CandidatePoolMembership,
    Person,
    ProviderGenreMap,
    ProviderTitleRecommendation,
    Title,
    TitleCredit,
    TitleGenre,
)
from screening_room.modules.catalog.providers.base import (
    MediaType,
    ProviderGenre,
    ProviderRef,
    TitleDetails,
    TitleSummary,
)

# (media type, provider genre id) -> internal genre ids, e.g. ("tv", 10765) -> [scifi, fantasy]
GenreMap = Mapping[tuple[str, int], Sequence[int]]

MAX_ERROR_LENGTH = 500


class UnmappedGenreError(Exception):
    """The provider used a genre our taxonomy doesn't map. Never dropped silently
    (catalog-ingestion.md §4.2): stop and update the mapping in a migration."""


# --- The candidate pool -------------------------------------------------------------------


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
        has_pool_membership(),
        Title.detail_level == "full",
        Title.provider_status == "active",
        Title.adult.is_(False),
    )


def has_pool_membership() -> ColumnElement[bool]:
    """SQL condition: a seed source put this `Title` in the pool."""
    return exists().where(CandidatePoolMembership.title_id == Title.id)


# --- Genres -------------------------------------------------------------------------------


def load_genre_map(session: Session, provider: str) -> dict[tuple[str, int], list[int]]:
    rows = session.execute(
        select(
            ProviderGenreMap.media_type,
            ProviderGenreMap.provider_genre_id,
            ProviderGenreMap.genre_id,
        )
        .where(ProviderGenreMap.provider == provider)
        .order_by(ProviderGenreMap.genre_id)
    )
    genre_map: dict[tuple[str, int], list[int]] = {}
    for media_type, provider_genre_id, genre_id in rows:
        genre_map.setdefault((media_type, provider_genre_id), []).append(genre_id)
    return genre_map


def check_genres_mapped(
    genre_map: GenreMap, media_type: MediaType, provider_genres: Iterable[ProviderGenre]
) -> None:
    """Fail before ingesting if the provider has any genre we can't map."""
    unmapped = [
        f"{g.id} {g.name!r}" for g in provider_genres if (media_type, g.id) not in genre_map
    ]
    if unmapped:
        raise UnmappedGenreError(
            f"{media_type} genres with no internal mapping: {', '.join(unmapped)}. "
            "Add them to the genre taxonomy with a migration."
        )


def internal_genre_ids(
    genre_map: GenreMap, media_type: MediaType, provider_genre_ids: Iterable[int]
) -> list[int]:
    """Internal genre ids in provider order, without repeats (two TV genres can
    both map to `adventure`, say). When one provider genre maps to several, they
    follow our taxonomy order (genre id): deterministic, and `position` is for
    display only, never ranking (data-model.md §3.2).

    TMDB genre ids are one shared id space across its movie and TV lists (every
    id in both means the same genre), and titles are sometimes tagged with a
    genre from the other list: e.g. a TV show tagged 10749 "Romance", which only
    the movie list offers. Those use the other media type's mapping. An id
    neither list knows still stops the run (catalog-ingestion.md §4.2).
    """
    other_media_type: MediaType = "tv" if media_type == "movie" else "movie"
    result: list[int] = []
    for provider_genre_id in provider_genre_ids:
        mapped = genre_map.get((media_type, provider_genre_id)) or genre_map.get(
            (other_media_type, provider_genre_id)
        )
        if mapped is None:
            raise UnmappedGenreError(
                f"{media_type} genre {provider_genre_id} has no internal mapping "
                "(in either TMDB genre list)"
            )
        result += [genre_id for genre_id in mapped if genre_id not in result]
    return result


# --- Writing titles -----------------------------------------------------------------------


def _summary_columns(summary: TitleSummary) -> dict[str, Any]:
    return {
        "name": summary.name,
        "original_name": summary.original_name,
        "overview": summary.overview,
        "original_language": summary.original_language,
        "release_date": summary.release_date,
        "poster_path": summary.poster_path,
        "backdrop_path": summary.backdrop_path,
        "popularity": summary.popularity,
        "vote_average": summary.vote_average,
        "vote_count": summary.vote_count,
        "adult": summary.adult,
    }


def upsert_title_summary(session: Session, summary: TitleSummary, synced_at: datetime) -> int:
    """Insert or update a title's list-level fields; returns its id.

    Never downgrades: `detail_level` is only set on insert, so a `full` title
    stays `full` when it shows up in a list again (catalog-ingestion.md §6).
    """
    columns = _summary_columns(summary)
    statement = (
        insert(Title)
        .values(
            provider=summary.ref.provider,
            media_type=summary.ref.media_type,
            provider_id=summary.ref.provider_id,
            detail_level="summary",
            summary_synced_at=synced_at,
            **columns,
        )
        .on_conflict_do_update(
            index_elements=[Title.provider, Title.media_type, Title.provider_id],
            set_={**columns, "summary_synced_at": synced_at},
        )
        .returning(Title.id)
    )
    title_id = session.scalar(statement)
    assert title_id is not None
    return title_id


def upsert_pool_membership(
    session: Session, title_id: int, source_key: str, source_rank: int, run_id: int
) -> None:
    """Record that `source_key` returned this title, at `source_rank`, in this run."""
    statement = insert(CandidatePoolMembership).values(
        title_id=title_id,
        source_key=source_key,
        source_rank=source_rank,
        first_seen_run_id=run_id,
        last_seen_run_id=run_id,
    )
    session.execute(
        statement.on_conflict_do_update(
            index_elements=[CandidatePoolMembership.title_id, CandidatePoolMembership.source_key],
            set_={"source_rank": source_rank, "last_seen_run_id": run_id},
        )
    )


def apply_title_details(
    session: Session,
    title_id: int,
    details: TitleDetails,
    genre_map: GenreMap,
    run_id: int | None,
    synced_at: datetime,
) -> None:
    """Hydrate a title: details, and its genres, credits and recommendation list
    replaced wholesale, so re-applying the same data changes nothing
    (catalog-ingestion.md §7-8). `run_id` is None for API read-through."""
    summary = details.summary
    genre_ids = internal_genre_ids(genre_map, summary.ref.media_type, summary.provider_genre_ids)

    session.execute(
        update(Title)
        .where(Title.id == title_id)
        .values(
            **_summary_columns(summary),
            imdb_id=details.imdb_id,
            runtime_minutes=details.runtime_minutes,
            number_of_seasons=details.number_of_seasons,
            detail_level="full",
            provider_status="active",
            summary_synced_at=synced_at,
            details_synced_at=synced_at,
            sync_error_count=0,
            last_sync_error=None,
            last_sync_error_at=None,
        )
    )

    session.execute(delete(TitleGenre).where(TitleGenre.title_id == title_id))
    session.add_all(
        TitleGenre(title_id=title_id, genre_id=genre_id, position=position)
        for position, genre_id in enumerate(genre_ids)
    )

    session.execute(delete(TitleCredit).where(TitleCredit.title_id == title_id))
    for credit in details.credits:
        person_id = _upsert_person(
            session,
            summary.ref.provider,
            credit.person_provider_id,
            credit.name,
            credit.profile_path,
        )
        session.add(
            TitleCredit(
                title_id=title_id,
                person_id=person_id,
                role=credit.role,
                character_name=credit.character_name,
                credit_order=credit.order,
            )
        )

    session.execute(
        delete(ProviderTitleRecommendation).where(
            ProviderTitleRecommendation.source_title_id == title_id
        )
    )
    session.add_all(
        ProviderTitleRecommendation(
            source_title_id=title_id,
            provider=target.provider,
            target_media_type=target.media_type,
            target_provider_id=target.provider_id,
            provider_rank=rank,
            fetched_at=synced_at,
            ingestion_run_id=run_id,
        )
        for rank, target in enumerate(details.recommendations, start=1)
    )
    session.flush()


def _upsert_person(
    session: Session, provider: str, provider_id: int, name: str, profile_path: str | None
) -> int:
    statement = (
        insert(Person)
        .values(provider=provider, provider_id=provider_id, name=name, profile_path=profile_path)
        .on_conflict_do_update(
            index_elements=[Person.provider, Person.provider_id],
            set_={"name": name, "profile_path": profile_path},
        )
        .returning(Person.id)
    )
    person_id = session.scalar(statement)
    assert person_id is not None
    return person_id


def mark_title_missing(session: Session, title_id: int) -> None:
    """The provider answered 404: keep the row, but leave the pool (data-model.md §6)."""
    session.execute(update(Title).where(Title.id == title_id).values(provider_status="missing"))


def record_sync_error(session: Session, title_id: int, message: str, at: datetime) -> None:
    """Count a failed hydration. Reset by the next successful one."""
    session.execute(
        update(Title)
        .where(Title.id == title_id)
        .values(
            sync_error_count=Title.sync_error_count + 1,
            last_sync_error=message[:MAX_ERROR_LENGTH],
            last_sync_error_at=at,
        )
    )


# --- Reading titles -----------------------------------------------------------------------


def titles_to_hydrate(
    session: Session, *, stale_before: datetime, include_summary_only: bool, limit: int | None
) -> list[tuple[int, ProviderRef]]:
    """Pool titles whose details are stale (and, for `ingest`, summary-only ones),
    oldest id first so runs are predictable (catalog-ingestion.md §7)."""
    needs_details = Title.details_synced_at < stale_before
    if include_summary_only:
        needs_details = or_(Title.detail_level == "summary", needs_details)
    rows = session.execute(
        select(Title.id, Title.provider, Title.media_type, Title.provider_id)
        .where(
            has_pool_membership(),
            Title.provider_status == "active",
            Title.adult.is_(False),
            needs_details,
        )
        .order_by(Title.id)
        .limit(limit)
    )
    return [
        (title_id, ProviderRef(provider, cast(MediaType, media_type), provider_id))
        for title_id, provider, media_type, provider_id in rows
    ]


def title_ids_for_refs(session: Session, refs: Iterable[ProviderRef]) -> dict[ProviderRef, int]:
    """Our ids for the titles we already have, by provider ref."""
    keys = [(ref.provider, ref.media_type, ref.provider_id) for ref in refs]
    if not keys:
        return {}
    rows = session.execute(
        select(Title.id, Title.provider, Title.media_type, Title.provider_id).where(
            tuple_(Title.provider, Title.media_type, Title.provider_id).in_(keys)
        )
    )
    return {
        ProviderRef(provider, cast(MediaType, media_type), provider_id): title_id
        for title_id, provider, media_type, provider_id in rows
    }


def pool_title_ids(session: Session, title_ids: Iterable[int]) -> set[int]:
    """Which of these titles already have a pool membership."""
    return set(
        session.scalars(
            select(CandidatePoolMembership.title_id)
            .where(CandidatePoolMembership.title_id.in_(list(title_ids)))
            .distinct()
        )
    )


def count_pool_titles(session: Session) -> int:
    """Titles with any pool membership (hydrated or not): what --max-titles caps."""
    count = session.scalar(select(func.count(CandidatePoolMembership.title_id.distinct())))
    return count or 0
