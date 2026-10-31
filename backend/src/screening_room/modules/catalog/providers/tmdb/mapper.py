"""TMDB JSON -> provider-neutral types (ADR-0004). The only code that knows TMDB's
response shapes. Pure functions, tested against recorded responses.

Movies and TV differ in field names:
    title / name, original_title / original_name, release_date / first_air_date,
    runtime / episode_run_time, directors (crew) / creators (created_by).
"""

from datetime import date
from typing import Any, cast

from screening_room.modules.catalog.providers.base import (
    Credit,
    ListPage,
    MediaType,
    ProviderError,
    ProviderGenre,
    ProviderRef,
    TitleDetails,
    TitleSummary,
)

PROVIDER = "tmdb"
MAX_CAST = 10  # top-billed cast only (data-model.md §3.2)

JSON = dict[str, Any]


def list_page(media_type: MediaType, data: JSON) -> ListPage:
    return ListPage(
        page=int(data.get("page", 1)),
        total_pages=int(data.get("total_pages", 1)),
        results=tuple(title_summary(media_type, item) for item in data.get("results", [])),
    )


def title_summary(media_type: MediaType, data: JSON) -> TitleSummary:
    """A list result, or the summary part of a details response."""
    is_movie = media_type == "movie"
    # List results carry `genre_ids`; details responses carry `genres` objects.
    genre_ids = data.get("genre_ids") or [genre["id"] for genre in data.get("genres", [])]
    return TitleSummary(
        ref=ProviderRef(PROVIDER, media_type, _required_int(data, "id")),
        name=_required_text(data, "title" if is_movie else "name"),
        original_name=_text(data.get("original_title" if is_movie else "original_name")),
        overview=_text(data.get("overview")),
        original_language=_text(data.get("original_language")),
        release_date=_date(data.get("release_date" if is_movie else "first_air_date")),
        poster_path=_text(data.get("poster_path")),
        backdrop_path=_text(data.get("backdrop_path")),
        popularity=_float(data.get("popularity")),
        vote_average=_float(data.get("vote_average")),
        vote_count=_int(data.get("vote_count")),
        adult=bool(data.get("adult", False)),
        provider_genre_ids=tuple(int(genre_id) for genre_id in genre_ids),
    )


def search_results(data: JSON) -> list[TitleSummary]:
    """A multi-search page: movies and TV only (not people), no adult titles.

    A malformed entry is skipped rather than failing the whole search.
    """
    results: list[TitleSummary] = []
    for item in data.get("results", []):
        media_type = item.get("media_type")
        if media_type not in ("movie", "tv") or item.get("adult"):
            continue
        try:
            results.append(title_summary(cast(MediaType, media_type), item))
        except ProviderError:
            continue
    return results


def title_details(media_type: MediaType, data: JSON) -> TitleDetails:
    """A details response fetched with append_to_response=credits,recommendations."""
    if media_type == "movie":
        runtime = _positive_int(data.get("runtime"))
        seasons = None
        imdb_id = _text(data.get("imdb_id"))
    else:
        # Typical episode length, when TMDB knows it (often an empty list).
        episode_runtimes = [m for m in data.get("episode_run_time") or [] if m and m > 0]
        runtime = episode_runtimes[0] if episode_runtimes else None
        seasons = _int(data.get("number_of_seasons"))
        imdb_id = None  # TV only has it under external_ids, which we don't fetch
    return TitleDetails(
        summary=title_summary(media_type, data),
        imdb_id=imdb_id,
        runtime_minutes=runtime,
        number_of_seasons=seasons,
        credits=_credits(media_type, data),
        recommendations=_recommendations(data),
    )


def genres(data: JSON) -> list[ProviderGenre]:
    return [ProviderGenre(id=int(g["id"]), name=str(g["name"])) for g in data.get("genres", [])]


# --- Details parts --------------------------------------------------------------------


def _credits(media_type: MediaType, data: JSON) -> tuple[Credit, ...]:
    """Top cast, plus directors (movies) or creators (TV). One entry per person and role."""
    credits_data: JSON = data.get("credits") or {}
    cast = sorted(credits_data.get("cast", []), key=lambda person: person.get("order", 0))
    result = [
        _credit(person, "cast", order, character=_text(person.get("character")))
        for order, person in enumerate(cast[:MAX_CAST])
    ]
    if media_type == "movie":
        crew = [p for p in credits_data.get("crew", []) if p.get("job") == "Director"]
        result += [_credit(person, "director", order) for order, person in enumerate(crew)]
    else:
        creators = data.get("created_by") or []
        result += [_credit(person, "creator", order) for order, person in enumerate(creators)]
    return _unique(result)


def _credit(person: JSON, role: Any, order: int, character: str | None = None) -> Credit:
    return Credit(
        person_provider_id=_required_int(person, "id"),
        name=_required_text(person, "name"),
        profile_path=_text(person.get("profile_path")),
        role=role,
        character_name=character,
        order=order,
    )


def _unique(credits: list[Credit]) -> tuple[Credit, ...]:
    """Drop repeats (e.g. someone listed twice as director), keeping the first."""
    seen: set[tuple[int, str]] = set()
    unique = []
    for credit in credits:
        key = (credit.person_provider_id, credit.role)
        if key not in seen:
            seen.add(key)
            unique.append(credit)
    return tuple(unique)


def _recommendations(data: JSON) -> tuple[ProviderRef, ...]:
    """TMDB's recommended titles, best first. Adult titles and non-movie/TV
    entries are skipped; duplicates keep their best rank."""
    refs: list[ProviderRef] = []
    for item in (data.get("recommendations") or {}).get("results", []):
        media_type = item.get("media_type")
        if item.get("adult") or media_type not in ("movie", "tv"):
            continue
        ref = ProviderRef(PROVIDER, media_type, _required_int(item, "id"))
        if ref not in refs:
            refs.append(ref)
    return tuple(refs)


# --- Field helpers: TMDB uses "", null or missing keys for "unknown" --------------------


def _text(value: Any) -> str | None:
    return value.strip() or None if isinstance(value, str) else None


def _int(value: Any) -> int | None:
    return int(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _positive_int(value: Any) -> int | None:
    number = _int(value)
    return number if number and number > 0 else None


def _float(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _date(value: Any) -> date | None:
    try:
        return date.fromisoformat(value) if isinstance(value, str) and value else None
    except ValueError:
        return None


def _required_int(data: JSON, key: str) -> int:
    value = _int(data.get(key))
    if value is None:
        raise ProviderError(f"TMDB response is missing {key!r}")
    return value


def _required_text(data: JSON, key: str) -> str:
    value = _text(data.get(key))
    if value is None:
        raise ProviderError(f"TMDB response is missing {key!r}")
    return value
