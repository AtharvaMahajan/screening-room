"""Record real TMDB responses as test fixtures (catalog-ingestion.md §12).

    uv run python -m tests.fixtures.tmdb.record [--only FILE ...]

Needs TMDB_API_TOKEN in .env. Makes one request per fixture (7), using the same
paths and parameters as TmdbProvider; --only records just the files named.
Re-run it to refresh the fixtures when TMDB's responses change; the mapper
tests then show what the change broke.
"""

import argparse
import json
from pathlib import Path

from screening_room.config import TmdbSettings
from screening_room.modules.catalog.providers.tmdb.client import TmdbClient
from screening_room.modules.catalog.providers.tmdb.provider import LANGUAGE

FIXTURES_DIR = Path(__file__).parent
DETAILS: dict[str, str | int] = {
    "language": LANGUAGE,
    "append_to_response": "credits,recommendations",
}

# fixture file -> (path, params)
REQUESTS: dict[str, tuple[str, dict[str, str | int]]] = {
    "genres_movie.json": ("/genre/movie/list", {"language": LANGUAGE}),
    "genres_tv.json": ("/genre/tv/list", {"language": LANGUAGE}),
    "movie_popular_page1.json": ("/movie/popular", {"language": LANGUAGE, "page": 1}),
    "tv_discover_scifi_page1.json": (
        "/discover/tv",
        {
            "language": LANGUAGE,
            "page": 1,
            "include_adult": "false",
            "with_genres": 10765,  # Sci-Fi & Fantasy
            "sort_by": "vote_count.desc",
            "vote_count.gte": 100,
        },
    ),
    "movie_329865_arrival.json": ("/movie/329865", DETAILS),
    "tv_1396_breaking_bad.json": ("/tv/1396", DETAILS),
    "search_multi_arrival.json": (
        "/search/multi",
        {"query": "arrival", "include_adult": "false", "language": LANGUAGE, "page": 1},
    ),
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", nargs="+", choices=sorted(REQUESTS), metavar="FILE")
    wanted = parser.parse_args().only or list(REQUESTS)
    settings = TmdbSettings()
    client = TmdbClient(settings.require_tmdb_token(), rate_limit_rps=4)
    try:
        for filename in wanted:
            path, params = REQUESTS[filename]
            data = client.get_json(path, params)
            text = json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
            (FIXTURES_DIR / filename).write_text(text, encoding="utf-8", newline="\n")
            print(f"recorded {path} -> {filename} ({len(text) // 1024} KB)")
    finally:
        client.close()


if __name__ == "__main__":
    main()
