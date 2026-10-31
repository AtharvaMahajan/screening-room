"""Load test POST /api/recommendations against the p95 < 1.5 s target (roadmap M5).

Run from backend/ against a running API (not the reloading dev server):

    uv run uvicorn screening_room.main:create_app --factory --port 8003
    uv run python scripts/load_test.py --base-url http://127.0.0.1:8003

Synthetic users are created straight in the database (DATABASE_URL), with
sessions, so registration's rate limit and password hashing stay out of the
measurement. They get realistic profiles: some cold starts, the rest with
liked genres, favorites, ratings, viewings, a watchlist and "not for me" titles.
They are all deleted afterwards (their request logs go with them by cascade),
even if the run fails.

Measures, per concurrency level:
- server time: rec_requests.latency_ms (retrieval + engine), which is what the
  target is defined on (overview.md §7)
- end to end: what the client waited, including queueing, the HTTP stack and
  logging the request
"""

import argparse
import random
import statistics
import threading
import time
import uuid
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx2
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from screening_room.config import Settings
from screening_room.db import create_db_engine
from screening_room.modules.catalog import service as catalog
from screening_room.modules.discovery.models import RecRequest
from screening_room.modules.identity import service as identity
from screening_room.modules.identity.models import User
from screening_room.modules.library import service as library
from screening_room.modules.profile import service as profile
from screening_room.modules.profile.schemas import PreferencesIn

EMAIL_DOMAIN = "load-test.invalid"  # never a real address; cleanup deletes by it


@dataclass(frozen=True)
class Sample:
    level: int
    status: int
    end_to_end_ms: float
    rec_request_id: int | None


def percentile(values: Sequence[float], p: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round(p / 100 * (len(ordered) - 1)))]


def create_users(session: Session, count: int, rng: random.Random, ttl_days: int) -> list[str]:
    """Users with varied profiles; returns their session tokens."""
    candidates = catalog.pool_candidates(session)
    by_votes = sorted(candidates, key=lambda c: (-(c.vote_count or 0), c.title_id))
    famous = [c.title_id for c in by_votes[:300]]
    everything = [c.title_id for c in candidates]
    genre_ids = [genre.id for genre in catalog.selectable_genres(session)]
    run = uuid.uuid4().hex[:8]
    tokens = []
    for n in range(count):
        user = User(email=f"user{n}-{run}@{EMAIL_DOMAIN}", password_hash="not-a-real-hash")
        session.add(user)
        session.flush()
        if rng.random() >= 0.2:  # 20% stay cold-start users
            liked = rng.sample(genre_ids, rng.randint(1, 3))
            profile.replace_preferences(session, user.id, PreferencesIn(liked_genre_ids=liked))
            for title_id in rng.sample(famous, rng.randint(1, 10)):
                profile.add_favorite(session, user.id, title_id)
            shelf = rng.sample(everything, 30)
            for title_id in shelf[: rng.randint(0, 15)]:
                library.rate(session, user.id, title_id, rng.randint(1, 5))
            for title_id in shelf[15 : 15 + rng.randint(0, 8)]:
                library.mark_watched(session, user.id, title_id)
            for title_id in shelf[23 : 23 + rng.randint(0, 4)]:
                library.add_to_watchlist(session, user.id, title_id)
            for title_id in shelf[27 : 27 + rng.randint(0, 3)]:
                library.mark_not_for_me(session, user.id, title_id)
        tokens.append(identity.create_session(session, user.id, ttl_days).token)
    session.commit()
    return tokens


def delete_users(session: Session) -> int:
    synthetic = User.email.endswith(f"@{EMAIL_DOMAIN}")
    count = session.scalar(select(func.count()).where(synthetic)) or 0
    session.execute(delete(User).where(synthetic))
    session.commit()
    return count


class Client:
    """One synthetic user's browser: session cookie plus its CSRF token."""

    def __init__(self, base_url: str, origin: str, cookie_name: str, token: str) -> None:
        self.http = httpx2.Client(base_url=base_url, cookies={cookie_name: token}, timeout=30)
        csrf = self.http.get("/api/auth/session").json()["csrf_token"]
        self.headers = {"Origin": origin, "X-CSRF-Token": csrf}
        self.lock = threading.Lock()  # one request at a time per user, like a person
        self.seen: list[int] = []

    def recommend(self, rng: random.Random, genre_ids: list[int], level: int) -> Sample:
        body: dict[str, object] = {
            "media_type": rng.choice(["any", "any", "movie", "tv"]),
            "genre_ids": [rng.choice(genre_ids)] if rng.random() < 0.3 else [],
            "max_runtime_minutes": rng.choice([90, 120, 150]) if rng.random() < 0.3 else None,
        }
        with self.lock:
            if self.seen and rng.random() < 0.3:  # "show me more"
                body["exclude_title_ids"] = self.seen[-100:]
            started = time.perf_counter()
            response = self.http.post("/api/recommendations", json=body, headers=self.headers)
            elapsed = (time.perf_counter() - started) * 1000
            data = response.json() if response.status_code == 200 else {}
            self.seen += [r["title"]["id"] for r in data.get("results", [])]
        return Sample(level, response.status_code, elapsed, data.get("request_id"))


def run_level(
    clients: list[Client], level: int, requests: int, genre_ids: list[int], seed: int
) -> tuple[list[Sample], float]:
    def one(i: int) -> Sample:
        rng = random.Random(seed * 1_000_003 + level * 10_007 + i)
        return clients[i % len(clients)].recommend(rng, genre_ids, level)

    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=level) as pool:
        samples = list(pool.map(one, range(requests)))
    return samples, time.perf_counter() - started


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8003")
    parser.add_argument("--origin", default="http://localhost:5173", help="an allowed origin")
    parser.add_argument("--users", type=int, default=40)
    parser.add_argument("--levels", default="1,5,10,20", help="concurrent clients per step")
    parser.add_argument("--requests", type=int, default=200, help="per level")
    parser.add_argument("--seed", type=int, default=2026)
    args = parser.parse_args()
    levels = [int(level) for level in args.levels.split(",")]
    rng = random.Random(args.seed)

    settings = Settings()
    engine = create_db_engine(settings.database_url)
    try:
        with Session(engine) as session:
            delete_users(session)  # leftovers from an interrupted run
            tokens = create_users(session, args.users, rng, settings.session_ttl_days)
            genre_ids = [genre.id for genre in catalog.selectable_genres(session)]
            pool_size = catalog.count_pool_titles(session)
        clients = [
            Client(args.base_url, args.origin, settings.session_cookie_name, t) for t in tokens
        ]
        run_level(clients, 2, 20, genre_ids, args.seed)  # warm-up, not counted
        results = [
            (level, *run_level(clients, level, args.requests, genre_ids, args.seed))
            for level in levels
        ]

        with Session(engine) as session:
            ids = [
                s.rec_request_id for _, samples, _ in results for s in samples if s.rec_request_id
            ]
            server_ms = {
                rec_id: latency
                for rec_id, latency in session.execute(
                    select(RecRequest.id, RecRequest.latency_ms).where(RecRequest.id.in_(ids))
                )
            }
        print_report(results, server_ms, pool_size, args)
    finally:
        with Session(engine) as session:
            print(f"\nCleanup: deleted {delete_users(session)} synthetic users and their logs.")
        engine.dispose()


def print_report(
    results: list[tuple[int, list[Sample], float]],
    server_ms: dict[int, int],
    pool_size: int,
    args: argparse.Namespace,
) -> None:
    print(f"Load test of POST /api/recommendations ({datetime.now(UTC):%Y-%m-%d %H:%M} UTC)")
    print(f"Pool: {pool_size} titles. {args.users} synthetic users, {args.requests} requests")
    print(f"per concurrency level, seed {args.seed}. Target: server p95 < 1500 ms.\n")
    print("Concurrent  req/s  errors   server p50   p95    max    end-to-end p50   p95    max")
    for level, samples, seconds in results:
        ok = [s for s in samples if s.status == 200]
        server = [float(server_ms[s.rec_request_id]) for s in ok if s.rec_request_id in server_ms]
        e2e = [s.end_to_end_ms for s in ok]
        errors = len(samples) - len(ok)
        print(
            f"{level:>10}  {len(samples) / seconds:>5.1f}  {errors:>6}   "
            f"{statistics.median(server):>9.0f} {percentile(server, 95):>6.0f} {max(server):>6.0f}"
            f"    {statistics.median(e2e):>13.0f} {percentile(e2e, 95):>6.0f} {max(e2e):>6.0f}"
        )


if __name__ == "__main__":
    main()
