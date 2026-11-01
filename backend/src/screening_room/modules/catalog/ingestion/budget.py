"""A request counter and budget around any provider (--max-requests).

Wrapping the provider keeps the phases unaware of budgets. It counts logical
requests: retries inside the TMDB client aren't counted separately.
"""

import threading

from screening_room.modules.catalog.providers.base import (
    CatalogProvider,
    ListPage,
    ListQuery,
    MediaType,
    ProviderGenre,
    ProviderRef,
    TitleDetails,
    TitleSummary,
)


class BudgetExhaustedError(Exception):
    """The run used all of --max-requests. Not a failure: re-running continues."""


class CountingProvider:
    def __init__(self, inner: CatalogProvider, max_requests: int | None = None) -> None:
        self.name = inner.name
        self._inner = inner
        self._max_requests = max_requests
        self._lock = threading.Lock()  # hydrate calls this from worker threads
        self.requests = 0

    def _spend(self) -> None:
        with self._lock:
            if self._max_requests is not None and self.requests >= self._max_requests:
                raise BudgetExhaustedError(f"request budget of {self._max_requests} reached")
            self.requests += 1

    def list_titles(self, query: ListQuery, page: int) -> ListPage:
        self._spend()
        return self._inner.list_titles(query, page)

    def get_details(self, ref: ProviderRef) -> TitleDetails:
        self._spend()
        return self._inner.get_details(ref)

    def list_genres(self, media_type: MediaType) -> list[ProviderGenre]:
        self._spend()
        return self._inner.list_genres(media_type)

    def search(self, query: str, media_type: MediaType | None = None) -> list[TitleSummary]:
        self._spend()
        return self._inner.search(query, media_type)
