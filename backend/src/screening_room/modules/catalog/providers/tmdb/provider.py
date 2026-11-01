"""The TMDB implementation of CatalogProvider: which endpoint answers which question."""

from screening_room.modules.catalog.providers.base import (
    ListPage,
    ListQuery,
    MediaType,
    ProviderGenre,
    ProviderRef,
    TitleDetails,
    TitleSummary,
)
from screening_room.modules.catalog.providers.tmdb import mapper
from screening_room.modules.catalog.providers.tmdb.client import TmdbClient

LANGUAGE = "en-US"  # MVP locale (ADR-0004)


class TmdbProvider:
    name = "tmdb"

    def __init__(self, client: TmdbClient) -> None:
        self._client = client

    def list_titles(self, query: ListQuery, page: int) -> ListPage:
        params: dict[str, str | int] = {**query.params, "language": LANGUAGE, "page": page}
        if query.endpoint == "discover":
            path = f"/discover/{query.media_type}"
            params["include_adult"] = "false"
        else:  # popular, top_rated
            path = f"/{query.media_type}/{query.endpoint}"
        return mapper.list_page(query.media_type, self._client.get_json(path, params))

    def get_details(self, ref: ProviderRef) -> TitleDetails:
        """Details, credits and page 1 of the recommendation list in one request."""
        data = self._client.get_json(
            f"/{ref.media_type}/{ref.provider_id}",
            {"language": LANGUAGE, "append_to_response": "credits,recommendations"},
        )
        return mapper.title_details(ref.media_type, data)

    def list_genres(self, media_type: MediaType) -> list[ProviderGenre]:
        data = self._client.get_json(f"/genre/{media_type}/list", {"language": LANGUAGE})
        return mapper.genres(data)

    def search(self, query: str, media_type: MediaType | None = None) -> list[TitleSummary]:
        """First page only (20 results). Both types: multi-search, people dropped.
        One type: that type's own search, so all 20 results are of it."""
        params: dict[str, str | int] = {
            "query": query,
            "include_adult": "false",
            "language": LANGUAGE,
            "page": 1,
        }
        if media_type is None:
            return mapper.search_results(self._client.get_json("/search/multi", params))
        page = mapper.list_page(media_type, self._client.get_json(f"/search/{media_type}", params))
        return [summary for summary in page.results if not summary.adult]
