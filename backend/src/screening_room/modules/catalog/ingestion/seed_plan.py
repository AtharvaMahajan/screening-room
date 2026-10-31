"""The seed plan: which provider lists fill the candidate pool (catalog-ingestion.md §4).

A typed, declarative list, so mypy checks it and no YAML parser is needed.
Growing the pool means editing this file (more sources or pages), not code.
"""

from dataclasses import dataclass

from screening_room.modules.catalog.providers.base import ListQuery, MediaType

SEED_PLAN_VERSION = "starter-v1"

MEDIA_TYPES: tuple[MediaType, ...] = ("movie", "tv")


@dataclass(frozen=True)
class SeedSource:
    key: str  # stable: memberships record it, e.g. "movie:discover:genre=horror"
    query: ListQuery
    pages: int  # 20 results per page


# TMDB genre id -> key name. Every genre except movie "TV Movie" and TV "News" and
# "Talk", which are poor fits for a "what to watch" shortlist.
SEEDED_GENRES: dict[MediaType, dict[int, str]] = {
    "movie": {
        28: "action",
        12: "adventure",
        16: "animation",
        35: "comedy",
        80: "crime",
        99: "documentary",
        18: "drama",
        10751: "family",
        14: "fantasy",
        36: "history",
        27: "horror",
        10402: "music",
        9648: "mystery",
        10749: "romance",
        878: "science-fiction",
        53: "thriller",
        10752: "war",
        37: "western",
    },
    "tv": {
        10759: "action-and-adventure",
        16: "animation",
        35: "comedy",
        80: "crime",
        99: "documentary",
        18: "drama",
        10751: "family",
        10762: "kids",
        9648: "mystery",
        10764: "reality",
        10765: "sci-fi-and-fantasy",
        10766: "soap",
        10768: "war-and-politics",
        37: "western",
    },
}
DECADES = range(1970, 2030, 10)  # 1970s ... 2020s
LANGUAGES = ("ko", "ja", "fr", "es", "hi", "de", "it", "zh")

# Quality floors (initial values): keep obscure titles with too few votes out.
VOTE_FLOOR: dict[MediaType, int] = {"movie": 200, "tv": 100}
LANGUAGE_VOTE_FLOOR: dict[MediaType, int] = {"movie": 50, "tv": 30}
# Movies are dated by release, TV by first air date.
DATE_FILTER: dict[MediaType, str] = {"movie": "primary_release_date", "tv": "first_air_date"}


def starter_v1() -> list[SeedSource]:
    sources: list[SeedSource] = []
    for media in MEDIA_TYPES:
        most_voted = {"sort_by": "vote_count.desc"}
        sources += [
            SeedSource(f"{media}:popular", ListQuery(media, "popular"), pages=3),
            SeedSource(f"{media}:top_rated", ListQuery(media, "top_rated"), pages=3),
        ]
        sources += [
            SeedSource(
                f"{media}:discover:genre={name}",
                ListQuery(
                    media,
                    "discover",
                    {"with_genres": genre_id, "vote_count.gte": VOTE_FLOOR[media], **most_voted},
                ),
                pages=2,
            )
            for genre_id, name in SEEDED_GENRES[media].items()
        ]
        sources += [
            SeedSource(
                f"{media}:discover:decade={decade}s",
                ListQuery(
                    media,
                    "discover",
                    {
                        f"{DATE_FILTER[media]}.gte": f"{decade}-01-01",
                        f"{DATE_FILTER[media]}.lte": f"{decade + 9}-12-31",
                        "vote_count.gte": VOTE_FLOOR[media],
                        **most_voted,
                    },
                ),
                pages=1,
            )
            for decade in DECADES
        ]
        sources += [
            SeedSource(
                f"{media}:discover:language={language}",
                ListQuery(
                    media,
                    "discover",
                    {
                        "with_original_language": language,
                        "vote_count.gte": LANGUAGE_VOTE_FLOOR[media],
                        **most_voted,
                    },
                ),
                pages=1,
            )
            for language in LANGUAGES
        ]
    return sources


PLANS = {SEED_PLAN_VERSION: starter_v1}
