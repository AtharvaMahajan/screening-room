"""Catalog use cases and queries.

Services never commit (project-structure.md §5.1): ingestion jobs and, from M2d,
the read-through helper own the transactions. The write functions here are
shared by both, so a title is stored the same way whichever path fetched it.
"""

from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime
from typing import Any, cast

from sqlalchemy import (
    ColumnElement,
    and_,
    case,
    delete,
    exists,
    func,
    or_,
    select,
    tuple_,
    update,
)
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from screening_room.modules.catalog.models import (
    CandidatePoolMembership,
    Genre,
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
from screening_room.modules.catalog.schemas import (
    CandidateFeatures,
    CastMember,
    GenreOut,
    TitleCardOut,
    TitlePreviewOut,
    TitleRecord,
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


def load_title_record(session: Session, title_id: int) -> TitleRecord | None:
    """A title with its genres and credits, as plain values (None if unknown)."""
    title = session.get(Title, title_id)
    if title is None:
        return None
    genres = session.execute(
        select(Genre.id, Genre.slug, Genre.name)
        .join(TitleGenre, TitleGenre.genre_id == Genre.id)
        .where(TitleGenre.title_id == title_id)
        .order_by(TitleGenre.position)
    ).all()
    credits = session.execute(
        select(TitleCredit.role, TitleCredit.character_name, Person.name, Person.profile_path)
        .join(Person, Person.id == TitleCredit.person_id)
        .where(TitleCredit.title_id == title_id)
        .order_by(TitleCredit.role, TitleCredit.credit_order)
    ).all()
    return TitleRecord(
        id=title.id,
        ref=ProviderRef(title.provider, cast(MediaType, title.media_type), title.provider_id),
        name=title.name,
        original_name=title.original_name,
        overview=title.overview,
        release_date=title.release_date,
        runtime_minutes=title.runtime_minutes,
        number_of_seasons=title.number_of_seasons,
        original_language=title.original_language,
        vote_average=title.vote_average,
        vote_count=title.vote_count,
        poster_path=title.poster_path,
        backdrop_path=title.backdrop_path,
        adult=title.adult,
        detail_level=title.detail_level,
        details_synced_at=title.details_synced_at,
        genres=tuple((genre_id, slug, name) for genre_id, slug, name in genres),
        cast=tuple(
            CastMember(name, character, profile)
            for role, character, name, profile in credits
            if role == "cast"
        ),
        directors=tuple(name for role, _, name, _ in credits if role == "director"),
        creators=tuple(name for role, _, name, _ in credits if role == "creator"),
    )


# --- Public queries for other modules (profile, discovery) ------------------------------------

# Image sizes TMDB serves; URLs are built from configuration (ADR-0004).
POSTER_SIZE = "w342"
BACKDROP_SIZE = "w780"
PROFILE_SIZE = "w185"

# Genres the seed plan deliberately skips (TMDB "TV Movie", "News", "Talk"):
# not offered as preferences or filters. See ingestion/seed_plan.py.
NON_SELECTABLE_GENRES = frozenset({"tv-movie", "news", "talk"})

SEARCH_LIMIT_MAX = 20


def image_url(base_url: str, size: str, path: str | None) -> str | None:
    return f"{base_url}/{size}{path}" if path else None


def selectable_genres(session: Session) -> list[GenreOut]:
    """The genres people can like, avoid or filter by, alphabetically."""
    rows = session.scalars(
        select(Genre).where(Genre.slug.not_in(NON_SELECTABLE_GENRES)).order_by(Genre.name)
    )
    return [GenreOut(id=genre.id, slug=genre.slug, name=genre.name) for genre in rows]


def is_candidate(session: Session, title_id: int) -> bool:
    """Is this title in the candidate pool (data-model.md §4)?"""
    return bool(session.scalar(select(exists().where(Title.id == title_id, in_candidate_pool()))))


def _card(title: Title, image_base_url: str) -> TitleCardOut:
    return TitleCardOut(
        id=title.id,
        media_type=cast(MediaType, title.media_type),
        name=title.name,
        year=title.release_date.year if title.release_date else None,
        poster_url=image_url(image_base_url, POSTER_SIZE, title.poster_path),
    )


def title_cards(
    session: Session, title_ids: Iterable[int], image_base_url: str
) -> dict[int, TitleCardOut]:
    """Card data for these titles, by id (titles that don't exist are left out)."""
    ids = list(title_ids)
    if not ids:
        return {}
    titles = session.scalars(select(Title).where(Title.id.in_(ids)))
    return {title.id: _card(title, image_base_url) for title in titles}


def title_previews(
    session: Session, title_ids: Iterable[int], image_base_url: str
) -> dict[int, TitlePreviewOut]:
    """Preview data for these titles, by id (titles that don't exist are left out)."""
    ids = list(title_ids)
    if not ids:
        return {}
    titles = session.scalars(select(Title).where(Title.id.in_(ids)))
    return {
        title.id: TitlePreviewOut(
            **_card(title, image_base_url).model_dump(),
            overview=title.overview,
            runtime_minutes=title.runtime_minutes,
        )
        for title in titles
    }


def _escape_like(text: str) -> str:
    """Make % and _ in user input match literally in a LIKE pattern."""
    return text.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")


def search_pool_titles(
    session: Session,
    *,
    query: str | None,
    media_type: MediaType | None,
    genre_ids: Sequence[int],
    limit: int,
    image_base_url: str,
) -> list[TitleCardOut]:
    """Find candidate-pool titles locally, never calling TMDB (catalog-ingestion.md §11).

    With `query`: a case-insensitive match on the name or original name. Names
    that START with the query come first, then well-known titles (most votes),
    because people searching for a favorite usually type a famous title.
    Without `query`: "popular in your genres" suggestions, most-voted first.
    """
    statement = select(Title).where(in_candidate_pool())
    if media_type is not None:
        statement = statement.where(Title.media_type == media_type)
    if genre_ids:
        statement = statement.where(
            exists().where(TitleGenre.title_id == Title.id, TitleGenre.genre_id.in_(genre_ids))
        )
    order_by: list[Any] = []
    if query:
        text = _escape_like(query.strip())
        statement = statement.where(
            or_(
                Title.name.ilike(f"%{text}%", escape="\\"),
                Title.original_name.ilike(f"%{text}%", escape="\\"),
            )
        )
        order_by.append(case((Title.name.ilike(f"{text}%", escape="\\"), 0), else_=1))
    order_by += [Title.vote_count.desc().nulls_last(), Title.id]
    titles = session.scalars(statement.order_by(*order_by).limit(min(limit, SEARCH_LIMIT_MAX)))
    return [_card(title, image_base_url) for title in titles]


# --- Retrieval for the recommender (recommendation-engine.md §5) -------------------------------


def pool_candidates(session: Session) -> list[CandidateFeatures]:
    """Every candidate-pool title with its genres and seed sources, by title id.

    The whole pool, unfiltered: pool statistics then don't depend on what the
    user asked for. Only the columns the engine uses: loading whole Title objects
    (overview text and all) took most of the request's time (M3 baseline).
    """
    titles = session.execute(
        select(
            Title.id,
            Title.media_type,
            Title.runtime_minutes,
            Title.release_date,
            Title.vote_average,
            Title.vote_count,
            Title.popularity,
        )
        .where(in_candidate_pool())
        .order_by(Title.id)
    ).all()
    pool_ids = select(Title.id).where(in_candidate_pool())
    genres: dict[int, set[int]] = {}
    for title_id, genre_id in session.execute(
        select(TitleGenre.title_id, TitleGenre.genre_id).where(TitleGenre.title_id.in_(pool_ids))
    ):
        genres.setdefault(title_id, set()).add(genre_id)
    sources: dict[int, set[str]] = {}
    for title_id, source_key in session.execute(
        select(CandidatePoolMembership.title_id, CandidatePoolMembership.source_key).where(
            CandidatePoolMembership.title_id.in_(pool_ids)
        )
    ):
        sources.setdefault(title_id, set()).add(source_key)
    return [
        CandidateFeatures(
            title_id=t.id,
            media_type=cast(MediaType, t.media_type),
            genre_ids=frozenset(genres.get(t.id, ())),
            runtime_minutes=t.runtime_minutes,
            release_date=t.release_date,
            vote_average=t.vote_average,
            vote_count=t.vote_count,
            popularity=t.popularity,
            source_keys=frozenset(sources.get(t.id, ())),
        )
        for t in titles
    ]


def pool_neighbors(
    session: Session, anchor_title_ids: Iterable[int]
) -> dict[int, list[tuple[int, int]]]:
    """Each anchor's provider recommendation list, resolved to CANDIDATE-POOL titles
    only, as (title id, provider rank), best rank first. Targets outside the pool
    are never recommended; they stay stored for coverage metrics (§5)."""
    anchors = list(anchor_title_ids)
    if not anchors:
        return {}
    rows = session.execute(
        select(
            ProviderTitleRecommendation.source_title_id,
            Title.id,
            ProviderTitleRecommendation.provider_rank,
        )
        .join(
            Title,
            and_(
                Title.provider == ProviderTitleRecommendation.provider,
                Title.media_type == ProviderTitleRecommendation.target_media_type,
                Title.provider_id == ProviderTitleRecommendation.target_provider_id,
            ),
        )
        .where(ProviderTitleRecommendation.source_title_id.in_(anchors), in_candidate_pool())
        .order_by(
            ProviderTitleRecommendation.source_title_id,
            ProviderTitleRecommendation.provider_rank,
            Title.id,
        )
    )
    neighbors: dict[int, list[tuple[int, int]]] = {}
    for anchor_id, title_id, rank in rows:
        neighbors.setdefault(anchor_id, []).append((title_id, rank))
    return neighbors


def genre_names(session: Session) -> dict[int, str]:
    """All internal genre names by id (including ones not offered as preferences)."""
    return {genre_id: name for genre_id, name in session.execute(select(Genre.id, Genre.name))}


def titles_with_genres(
    session: Session, title_ids: Iterable[int]
) -> dict[int, tuple[str, frozenset[int]]]:
    """(name, genre ids) for these titles, e.g. the user's favorites."""
    ids = list(title_ids)
    if not ids:
        return {}
    names = {
        title_id: name
        for title_id, name in session.execute(select(Title.id, Title.name).where(Title.id.in_(ids)))
    }
    genres: dict[int, set[int]] = {}
    for title_id, genre_id in session.execute(
        select(TitleGenre.title_id, TitleGenre.genre_id).where(TitleGenre.title_id.in_(ids))
    ):
        genres.setdefault(title_id, set()).add(genre_id)
    return {tid: (name, frozenset(genres.get(tid, ()))) for tid, name in names.items()}
