"""TMDB HTTP behaviour against a fake transport: retries, Retry-After, errors,
rate limiting and secret hygiene (catalog-ingestion.md §10). No network."""

import logging
from collections.abc import Callable, Iterator

import httpx2 as httpx
import pytest

from screening_room.modules.catalog.providers.base import (
    ListQuery,
    ProviderAuthError,
    ProviderError,
    ProviderNotFoundError,
    ProviderRef,
    ProviderUnavailableError,
)
from screening_room.modules.catalog.providers.tmdb.client import RateLimiter, TmdbClient
from screening_room.modules.catalog.providers.tmdb.provider import TmdbProvider

TOKEN = "test-token-that-must-never-be-logged"
Responder = Callable[[httpx.Request], httpx.Response]


class SpyLimiter(RateLimiter):
    """Never waits; records pauses."""

    def __init__(self) -> None:
        super().__init__(1e9, sleep=lambda _: None)
        self.pauses: list[float] = []

    def pause(self, seconds: float) -> None:
        self.pauses.append(seconds)


class Fake:
    """A scripted TMDB: each request gets the next response (or exception)."""

    def __init__(self, *responses: httpx.Response | Exception) -> None:
        self._responses: Iterator[httpx.Response | Exception] = iter(responses)
        self.requests: list[httpx.Request] = []
        self.sleeps: list[float] = []
        self.limiter = SpyLimiter()

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        response = next(self._responses)
        if isinstance(response, Exception):
            raise response
        return response

    def client(self, max_attempts: int = 3) -> TmdbClient:
        return TmdbClient(
            TOKEN,
            max_attempts=max_attempts,
            transport=httpx.MockTransport(self.handle),
            limiter=self.limiter,
            sleep=self.sleeps.append,
            jitter=lambda: 0.0,  # deterministic backoff
        )


def ok(data: object = None) -> httpx.Response:
    return httpx.Response(200, json=data if data is not None else {"ok": True})


# --- Success --------------------------------------------------------------------------------


def test_sends_the_token_as_a_bearer_header_and_returns_json() -> None:
    fake = Fake(ok({"genres": []}))

    data = fake.client().get_json("/genre/movie/list", {"language": "en-US"})

    assert data == {"genres": []}
    request = fake.requests[0]
    assert request.headers["authorization"] == f"Bearer {TOKEN}"
    assert request.url.path == "/3/genre/movie/list"
    assert request.url.params["language"] == "en-US"
    assert TOKEN not in str(request.url)  # never in the URL, where it would be logged


# --- Retries --------------------------------------------------------------------------------


def test_server_errors_are_retried_with_exponential_backoff() -> None:
    fake = Fake(httpx.Response(503), httpx.Response(502), ok())

    assert fake.client().get_json("/movie/1") == {"ok": True}
    assert fake.sleeps == [0.5, 1.0]


@pytest.mark.parametrize(
    "error", [httpx.ConnectTimeout("slow"), httpx.ReadTimeout("slow"), httpx.ConnectError("down")]
)
def test_timeouts_and_connection_errors_are_retried(error: Exception) -> None:
    fake = Fake(error, ok())

    assert fake.client().get_json("/movie/1") == {"ok": True}
    assert len(fake.requests) == 2


def test_gives_up_after_max_attempts() -> None:
    fake = Fake(httpx.Response(500), httpx.Response(500), httpx.Response(500))

    with pytest.raises(ProviderUnavailableError):
        fake.client(max_attempts=3).get_json("/movie/1")
    assert len(fake.requests) == 3
    assert fake.sleeps == [0.5, 1.0]  # no pointless wait after the last attempt


def test_user_facing_paths_retry_at_most_once() -> None:
    fake = Fake(httpx.Response(500), httpx.Response(500))

    with pytest.raises(ProviderUnavailableError):
        fake.client(max_attempts=2).get_json("/movie/1")
    assert len(fake.requests) == 2


def test_429_honours_retry_after_and_slows_every_thread() -> None:
    fake = Fake(httpx.Response(429, headers={"Retry-After": "2"}), ok())

    assert fake.client().get_json("/movie/1") == {"ok": True}
    assert fake.sleeps == [2.0]
    assert fake.limiter.pauses == [2.0]  # the shared limiter holds everyone back


@pytest.mark.parametrize(
    ("retry_after", "expected_wait"),
    [("not-a-number", 0.5), ("3600", 60.0)],  # bad value: backoff; huge value: capped
)
def test_429_with_unusable_retry_after(retry_after: str, expected_wait: float) -> None:
    fake = Fake(httpx.Response(429, headers={"Retry-After": retry_after}), ok())

    fake.client().get_json("/movie/1")

    assert fake.sleeps == [expected_wait]


def test_backoff_adds_jitter() -> None:
    fake = Fake(httpx.Response(500), ok())
    client = TmdbClient(
        TOKEN,
        transport=httpx.MockTransport(fake.handle),
        limiter=fake.limiter,
        sleep=fake.sleeps.append,
        jitter=lambda: 1.0,  # maximum jitter: +50%
    )

    client.get_json("/movie/1")

    assert fake.sleeps == [0.75]


# --- Errors that are never retried ------------------------------------------------------------


def test_404_means_missing_and_is_not_retried() -> None:
    fake = Fake(httpx.Response(404))

    with pytest.raises(ProviderNotFoundError):
        fake.client().get_json("/movie/999999999")
    assert len(fake.requests) == 1


@pytest.mark.parametrize("status", [401, 403])
def test_bad_credentials_stop_immediately(status: int) -> None:
    fake = Fake(httpx.Response(status))

    with pytest.raises(ProviderAuthError):
        fake.client().get_json("/movie/1")
    assert len(fake.requests) == 1


def test_other_client_errors_are_not_retried() -> None:
    fake = Fake(httpx.Response(400))

    with pytest.raises(ProviderError):
        fake.client().get_json("/movie/1")
    assert len(fake.requests) == 1


# --- Secret hygiene (security.md §9) ---------------------------------------------------------


def test_the_token_never_appears_in_logs_or_errors(caplog: pytest.LogCaptureFixture) -> None:
    fake = Fake(httpx.Response(500), httpx.ReadTimeout("slow"), httpx.Response(401))
    caplog.set_level(logging.DEBUG)

    with pytest.raises(ProviderAuthError) as raised:
        fake.client().get_json("/movie/1")

    assert caplog.records, "expected the retries to be logged"
    assert TOKEN not in caplog.text
    assert TOKEN not in str(raised.value)


# --- Rate limiter ----------------------------------------------------------------------------


class FakeClock:
    def __init__(self) -> None:
        self.now = 100.0
        self.sleeps: list[float] = []

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(round(seconds, 6))


def test_rate_limiter_spaces_requests_evenly() -> None:
    clock = FakeClock()
    limiter = RateLimiter(10, clock=lambda: clock.now, sleep=clock.sleep)

    for _ in range(3):
        limiter.acquire()  # three requests at the same instant

    assert clock.sleeps == [0.1, 0.2]  # no burst: 10/s means one every 0.1 s


def test_rate_limiter_pause_holds_back_the_next_request() -> None:
    clock = FakeClock()
    limiter = RateLimiter(10, clock=lambda: clock.now, sleep=clock.sleep)

    limiter.pause(5.0)
    limiter.acquire()

    assert clock.sleeps == [5.0]


# --- TmdbProvider: which endpoint answers which question --------------------------------------


def provider_with(fake: Fake) -> TmdbProvider:
    return TmdbProvider(fake.client())


def test_discover_excludes_adult_titles_and_passes_filters() -> None:
    fake = Fake(ok({"page": 2, "total_pages": 5, "results": []}))
    query = ListQuery("tv", "discover", {"with_genres": 10765, "sort_by": "vote_count.desc"})

    page = provider_with(fake).list_titles(query, page=2)

    request = fake.requests[0]
    assert request.url.path == "/3/discover/tv"
    assert request.url.params["include_adult"] == "false"
    assert request.url.params["with_genres"] == "10765"
    assert request.url.params["page"] == "2"
    assert request.url.params["language"] == "en-US"
    assert (page.page, page.total_pages) == (2, 5)


def test_popular_uses_the_media_type_list_endpoint() -> None:
    fake = Fake(ok({"page": 1, "total_pages": 1, "results": []}))

    provider_with(fake).list_titles(ListQuery("movie", "popular"), page=1)

    assert fake.requests[0].url.path == "/3/movie/popular"


def test_details_fetch_credits_and_recommendations_in_one_request() -> None:
    fake = Fake(ok({"id": 1396, "name": "Breaking Bad"}))

    details = provider_with(fake).get_details(ProviderRef("tmdb", "tv", 1396))

    assert len(fake.requests) == 1
    assert fake.requests[0].url.path == "/3/tv/1396"
    assert fake.requests[0].url.params["append_to_response"] == "credits,recommendations"
    assert details.summary.name == "Breaking Bad"


def test_search_for_both_types_uses_multi_search() -> None:
    fake = Fake(ok({"page": 1, "results": []}))

    provider_with(fake).search("arrival")

    request = fake.requests[0]
    assert request.url.path == "/3/search/multi"
    assert (request.url.params["query"], request.url.params["include_adult"]) == (
        "arrival",
        "false",
    )


def test_search_for_one_type_uses_that_types_search_and_drops_adult_titles() -> None:
    fake = Fake(
        ok(
            {
                "page": 1,
                "results": [
                    {"id": 1, "name": "Dark", "first_air_date": "2017-12-01"},
                    {"id": 2, "name": "Not for here", "adult": True},
                ],
            }
        )
    )

    results = provider_with(fake).search("dark", "tv")

    assert fake.requests[0].url.path == "/3/search/tv"
    assert [(r.ref.media_type, r.name) for r in results] == [("tv", "Dark")]
