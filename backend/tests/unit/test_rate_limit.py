"""The fixed-window limiter behind login and registration limits (security.md §8)."""

from screening_room.core.rate_limit import FixedWindowLimiter


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_a_key_is_refused_once_it_reaches_the_limit() -> None:
    clock = FakeClock()
    limiter = FixedWindowLimiter(limit=3, window_seconds=60, clock=clock)

    for _ in range(3):
        assert limiter.retry_after("ip") is None
        limiter.hit("ip")
    clock.now += 20

    assert limiter.retry_after("ip") == 40  # the window started 20 s ago
    assert limiter.retry_after("other") is None  # keys are independent


def test_the_window_restarts_after_it_ends() -> None:
    clock = FakeClock()
    limiter = FixedWindowLimiter(limit=1, window_seconds=60, clock=clock)
    limiter.hit("ip")

    clock.now += 60

    assert limiter.retry_after("ip") is None
    limiter.hit("ip")
    assert limiter.retry_after("ip") == 60


def test_retry_after_is_at_least_one_second() -> None:
    clock = FakeClock()
    limiter = FixedWindowLimiter(limit=1, window_seconds=60, clock=clock)
    limiter.hit("ip")

    clock.now += 59.9

    assert limiter.retry_after("ip") == 1


def test_memory_stays_bounded_with_many_keys() -> None:
    clock = FakeClock()
    limiter = FixedWindowLimiter(limit=1, window_seconds=60, clock=clock, max_keys=100)

    for i in range(1000):
        clock.now += 0.001
        limiter.hit(f"ip-{i}")

    assert len(limiter._windows) <= 100
    assert limiter.retry_after("ip-999") is not None  # the newest keys are kept
