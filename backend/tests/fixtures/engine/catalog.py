"""The engine's fixture catalog and personas (recommendation-engine.md §14).

155 titles: 15 themes x 10 titles across genres, decades and both media types,
plus 5 deliberately ineligible ones. Values come from simple formulas, not
randomness, so the catalog is identical every time. Titles recommend others in
their theme, except the "Indie Gem" theme, whose lists are empty: the fallback
case for favorite_neighbor.
"""

from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime
from typing import Any

from screening_room.modules.discovery.engine.types import (
    Candidate,
    Favorite,
    LibraryTitle,
    MediaType,
    Neighbor,
    PoolStats,
    RatedTitle,
    RecommendationContext,
    UserSignals,
)

AS_OF = date(2026, 6, 1)

GENRES = {
    "action": 1,
    "adventure": 2,
    "animation": 3,
    "comedy": 4,
    "crime": 5,
    "documentary": 6,
    "drama": 7,
    "family": 8,
    "fantasy": 9,
    "horror": 10,
    "mystery": 11,
    "romance": 12,
    "science-fiction": 13,
    "thriller": 14,
    "war": 15,
    "western": 16,
}
GENRE_NAMES = {gid: slug.replace("-", " ").title() for slug, gid in GENRES.items()}

# (name prefix, media type, genres, has recommendation lists)
THEMES: list[tuple[str, MediaType, tuple[str, ...], bool]] = [
    ("Space Saga", "movie", ("science-fiction", "adventure"), True),
    ("Cyber Noir", "movie", ("science-fiction", "thriller"), True),
    ("Laugh Track", "movie", ("comedy",), True),
    ("Rom Com", "movie", ("comedy", "romance"), True),
    ("Haunted", "movie", ("horror", "thriller"), True),
    ("Slasher", "movie", ("horror",), True),
    ("Family Fun", "movie", ("animation", "family", "comedy"), True),
    ("Prestige Drama", "movie", ("drama",), True),
    ("Heist", "movie", ("crime", "thriller"), True),
    ("Indie Gem", "movie", ("drama", "romance"), False),  # empty lists: fallback case
    ("Frontier", "movie", ("western", "action"), True),
    ("Docu", "movie", ("documentary",), True),
    ("Family Saga", "tv", ("drama",), True),
    ("Star Voyage", "tv", ("science-fiction", "fantasy", "adventure"), True),
    ("Sitcom", "tv", ("comedy",), True),
]
TITLES_PER_THEME = 10


def title_id(theme_index: int, i: int) -> int:
    return 100 * (theme_index + 1) + i


# Each title adds one extra genre in a repeating pattern, so a theme has 5
# different genre sets (real titles vary; identical sets trip the near-duplicate rule).
EXTRA_GENRES: tuple[tuple[str, ...], ...] = ((), ("mystery",), ("crime",), ("romance",), ("war",))


def _themed_candidate(theme_index: int, i: int) -> Candidate:
    _, media, theme_genres, _ = THEMES[theme_index]
    genres = theme_genres + EXTRA_GENRES[i % len(EXTRA_GENRES)]
    year = 1975 + (i * 7 + theme_index * 3) % 50
    source = ("top_rated", "popular", "discover:genre=x")[i % 3]
    return Candidate(
        title_id=title_id(theme_index, i),
        media_type=media,
        genre_ids=frozenset(GENRES[g] for g in genres),
        runtime_minutes=75 + (i * 13 + theme_index * 7) % 90 if media == "movie" else None,
        release_date=date(year, 1 + i % 12, 15),
        vote_average=5.0 + ((i * 37 + theme_index * 11) % 40) / 10,
        vote_count=20 + (i * 977 + theme_index * 131) % 15000,
        popularity=1.0 + (i * 53 + theme_index * 29) % 400,
        source_keys=frozenset({f"{media}:{source}"}),
    )


def _special(title: int, **overrides: Any) -> Candidate:
    base = Candidate(
        title_id=title,
        media_type="movie",
        genre_ids=frozenset({GENRES["science-fiction"]}),
        runtime_minutes=100,
        release_date=date(2010, 1, 1),
        vote_average=9.5,  # very good: they must be excluded for the right reason
        vote_count=50000,
        popularity=500.0,
        source_keys=frozenset({"movie:top_rated"}),
    )
    return replace(base, **overrides)


# Ineligible on purpose, each for one rule.
SPECIAL = {
    "unreleased": _special(9001, release_date=date(2030, 1, 1)),
    # Ineligible only when a runtime limit is set; otherwise an ordinary title.
    "unknown_runtime": _special(
        9002,
        genre_ids=frozenset({GENRES["comedy"]}),
        runtime_minutes=None,
        vote_average=7.0,
        vote_count=800,
        popularity=40.0,
    ),
    "adult": _special(9003, adult=True),
    "summary_only": _special(9004, detail_level="summary"),
    "missing": _special(9005, provider_status="missing"),
}


def candidates() -> list[Candidate]:
    themed = [_themed_candidate(t, i) for t in range(len(THEMES)) for i in range(TITLES_PER_THEME)]
    return themed + list(SPECIAL.values())


def name_of(title: int) -> str:
    theme_index, i = divmod(title, 100)
    return f"{THEMES[theme_index - 1][0]} {i}"


def neighbor_index() -> dict[int, tuple[Neighbor, ...]]:
    """Each title's TMDB-style list: the rest of its theme, nearest first."""
    index: dict[int, tuple[Neighbor, ...]] = {}
    for t, (_, _, _, has_lists) in enumerate(THEMES):
        for i in range(TITLES_PER_THEME):
            others = sorted(
                (j for j in range(TITLES_PER_THEME) if j != i), key=lambda j: (abs(i - j), j)
            )
            index[title_id(t, i)] = (
                tuple(Neighbor(title_id(t, j), rank) for rank, j in enumerate(others, start=1))
                if has_lists
                else ()
            )
    return index


def pool_stats(items: list[Candidate]) -> PoolStats:
    votes = [c.vote_average for c in items if c.vote_average is not None]
    return PoolStats(
        mean_vote_average=sum(votes) / len(votes),
        max_popularity=max(c.popularity or 0 for c in items),
        pool_size=len(items),
    )


def favorite(title: int, picked_day: int) -> Favorite:
    theme = THEMES[title // 100 - 1]
    return Favorite(
        title_id=title,
        name=name_of(title),
        genre_ids=frozenset(GENRES[g] for g in theme[2]),
        picked_at=datetime(2026, 5, picked_day, tzinfo=UTC),
    )


def genres_of(title: int) -> frozenset[int]:
    return frozenset(GENRES[g] for g in THEMES[title // 100 - 1][2])


def rated(title: int, stars: int, rated_day: int) -> RatedTitle:
    return RatedTitle(
        title_id=title,
        name=name_of(title),
        genre_ids=genres_of(title),
        stars=stars,
        rated_at=datetime(2026, 5, rated_day, tzinfo=UTC),
    )


def shelf(*titles: int) -> tuple[LibraryTitle, ...]:
    return tuple(LibraryTitle(title, genres_of(title)) for title in titles)


# --- Personas (§14) ---------------------------------------------------------------------


@dataclass(frozen=True)
class Persona:
    name: str
    signals: UserSignals
    context: RecommendationContext = field(default_factory=RecommendationContext)


PERSONAS = [
    Persona("new_user", UserSignals()),
    Persona(
        "scifi_fan",
        UserSignals(
            liked_genre_ids=frozenset({GENRES["science-fiction"]}),
            favorites=(favorite(100, 1), favorite(101, 2)),  # Space Saga 0 and 1
        ),
    ),
    Persona(
        "comedy_movie_under_90",
        UserSignals(liked_genre_ids=frozenset({GENRES["comedy"]})),
        RecommendationContext(
            media_type="movie", genre_ids=frozenset({GENRES["comedy"]}), max_runtime_minutes=90
        ),
    ),
    Persona(
        "tv_drama_fan",
        UserSignals(liked_genre_ids=frozenset({GENRES["drama"]})),
        RecommendationContext(media_type="tv"),
    ),
    Persona(
        "horror_avoider",
        UserSignals(
            liked_genre_ids=frozenset({GENRES["thriller"]}),
            avoided_genre_ids=frozenset({GENRES["horror"]}),
        ),
    ),
    Persona(
        "no_usable_neighbors",
        # Indie Gem favorites: their recommendation lists are empty.
        UserSignals(favorites=(favorite(1000, 1), favorite(1001, 2))),
    ),
    Persona(
        "library_user",
        # M4: no onboarding at all, only library activity.
        UserSignals(
            ratings=(rated(900, 5, 3), rated(1100, 1, 4)),  # Heist 0 loved, Frontier 0 hated
            watched=shelf(900, 1100, 901),  # Heist 1 watched, not rated
            watchlist=shelf(800),  # Prestige Drama 0 saved
            not_for_me=shelf(902),  # Heist 2 turned down
        ),
    ),
]
PERSONAS_BY_NAME = {p.name: p for p in PERSONAS}
