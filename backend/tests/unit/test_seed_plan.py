"""The starter-v1 seed plan (catalog-ingestion.md §4.1) and the jobs CLI's dry run."""

import importlib.util

import pytest

from screening_room.jobs import main
from screening_room.modules.catalog.ingestion.seed_plan import SEEDED_GENRES, starter_v1
from screening_room.modules.catalog.service import NON_SELECTABLE_GENRES
from tests.unit.test_tmdb_mapper import MIGRATION_0003, fixture


def test_plan_matches_the_documented_shape() -> None:
    sources = starter_v1()
    by_media = {
        media: [s for s in sources if s.query.media_type == media] for media in ("movie", "tv")
    }

    # popular 3 + top rated 3 + 2 per genre + 6 decades + 8 languages
    assert sum(s.pages for s in by_media["movie"]) == 3 + 3 + 18 * 2 + 6 + 8 == 56
    assert sum(s.pages for s in by_media["tv"]) == 3 + 3 + 14 * 2 + 6 + 8 == 48
    assert len({s.key for s in sources}) == len(sources), "source keys must be unique"


def test_poor_fit_genres_are_not_seeded() -> None:
    assert 10770 not in SEEDED_GENRES["movie"]  # TV Movie
    assert {10763, 10767}.isdisjoint(SEEDED_GENRES["tv"])  # News, Talk


@pytest.mark.parametrize("media", ["movie", "tv"])
def test_every_seeded_genre_is_a_real_tmdb_genre(media: str) -> None:
    real = {genre["id"] for genre in fixture(f"genres_{media}.json")["genres"]}

    assert set(SEEDED_GENRES[media]) <= real  # type: ignore[index]


def test_discover_queries_have_vote_floors() -> None:
    discover = [s for s in starter_v1() if s.query.endpoint == "discover"]

    assert discover
    assert all("vote_count.gte" in s.query.params for s in discover)
    assert all(s.query.params["sort_by"] == "vote_count.desc" for s in discover)


def test_dry_run_prints_the_plan_without_needing_a_database(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    # No database or token configured: a dry run must not need either.
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("TMDB_API_TOKEN", raising=False)

    exit_code = main(["ingest", "--dry-run", "--media", "movie", "--max-requests", "50"])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "34 sources" in output  # popular, top rated, 18 genres, 6 decades, 8 languages
    assert "up to 56 list requests" in output
    assert "stops after 50 requests" in output


def test_non_selectable_genres_are_exactly_the_ones_the_plan_skips() -> None:
    """Onboarding hides a genre only if no seeded TMDB genre maps to it."""
    spec = importlib.util.spec_from_file_location("migration_0003", MIGRATION_0003)
    assert spec and spec.loader
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    seeded_slugs = {
        slug
        for media, genres in migration.TMDB_GENRES.items()
        for tmdb_id, (_, slugs) in genres.items()
        if tmdb_id in SEEDED_GENRES[media]
        for slug in slugs
    }
    all_slugs = {slug for slug, _ in migration.GENRES}

    assert all_slugs - seeded_slugs == NON_SELECTABLE_GENRES
