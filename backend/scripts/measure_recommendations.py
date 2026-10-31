"""Measure the recommender on the real candidate pool (roadmap M3: latency baseline).

Run from backend/ against the dev database (after `jobs ingest`):

    uv run python scripts/measure_recommendations.py [--requests 300] [--seed 2026]

Everything runs inside one transaction that is rolled back at the end, so the
database is left exactly as it was. Prints a plain-text report.

What it measures:
- Latency of the recommendation service, as logged in rec_requests.latency_ms
  (retrieval + engine), and end to end including the log inserts.
- Neighbor coverage: how many pool titles have TMDB recommendations that land
  in the pool, i.e. how often a favorite can produce "Because you picked ...".

The workload is synthetic but shaped like real use: some cold-start users, and
favorites drawn from the most-voted titles, since that's what search surfaces.
"""

import argparse
import random
import statistics
import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from screening_room.config import DatabaseSettings
from screening_room.db import create_db_engine
from screening_room.modules.catalog import service as catalog
from screening_room.modules.discovery import service as discovery
from screening_room.modules.discovery.models import RecRequest
from screening_room.modules.discovery.schemas import RecommendationRequestIn
from screening_room.modules.identity.models import User
from screening_room.modules.profile import service as profile
from screening_room.modules.profile.schemas import PreferencesIn

FAVORITES_FROM_TOP = 300  # favorites are drawn from this many most-voted pool titles
WARM_UP = 10  # requests run first and not counted (imports, caches, query plans)


@dataclass(frozen=True)
class Sample:
    service_ms: int  # what rec_requests.latency_ms records
    total_ms: float  # including the log inserts
    results: int
    anchors: int
    anchors_without_neighbors: int
    neighbor_reasons: int


def percentile(values: Sequence[float], p: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round(p / 100 * (len(ordered) - 1)))]


def random_request(rng: random.Random, genre_ids: list[int]) -> RecommendationRequestIn:
    return RecommendationRequestIn(
        media_type=rng.choice(["any", "any", "movie", "tv"]),
        genre_ids=[rng.choice(genre_ids)] if rng.random() < 0.3 else [],
        max_runtime_minutes=rng.choice([90, 120, 150]) if rng.random() < 0.3 else None,
        limit=5,
    )


def one_request(
    session: Session, rng: random.Random, user_id: int, top_ids: list[int], genre_ids: list[int]
) -> Sample:
    savepoint = session.begin_nested()  # undo this user's profile and logs afterwards
    if rng.random() >= 0.2:  # 20% stay cold-start users
        liked = rng.sample(genre_ids, rng.randint(1, 3))
        profile.replace_preferences(session, user_id, PreferencesIn(liked_genre_ids=liked))
        for title_id in rng.sample(top_ids, rng.randint(1, 10)):
            profile.add_favorite(session, user_id, title_id)
        session.flush()

    started = time.perf_counter()
    out = discovery.recommend_for_user(session, user_id, random_request(rng, genre_ids), "")
    total_ms = (time.perf_counter() - started) * 1000
    logged = session.get(RecRequest, out.request_id)
    assert logged is not None
    sample = Sample(
        service_ms=logged.latency_ms,
        total_ms=total_ms,
        results=len(out.results),
        anchors=logged.anchor_count,
        anchors_without_neighbors=logged.anchors_without_neighbors,
        neighbor_reasons=sum(
            any(reason.type == "favorite_neighbor" for reason in r.reasons) for r in out.results
        ),
    )
    savepoint.rollback()
    return sample


def coverage_lines(session: Session, label: str, title_ids: list[int]) -> list[str]:
    neighbors = catalog.pool_neighbors(session, title_ids)
    counts = [len(neighbors.get(title_id, [])) for title_id in title_ids]
    with_any = sum(count > 0 for count in counts)
    return [
        f"{label}: {len(title_ids)} titles",
        f"  with >= 1 pool neighbor: {with_any} ({with_any / len(title_ids):.0%})",
        f"  with >= 3 pool neighbors: {sum(c >= 3 for c in counts)}",
        f"  pool neighbors per title: median {statistics.median(counts):g},"
        f" mean {statistics.mean(counts):.1f}, max {max(counts)}",
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--requests", type=int, default=300)
    parser.add_argument("--seed", type=int, default=2026)
    args = parser.parse_args()
    rng = random.Random(args.seed)

    engine = create_db_engine(DatabaseSettings().database_url)
    with engine.connect() as connection, Session(bind=connection) as session:
        connection.begin()
        try:
            candidates = catalog.pool_candidates(session)
            by_votes = sorted(candidates, key=lambda c: (-(c.vote_count or 0), c.title_id))
            top_ids = [c.title_id for c in by_votes[:FAVORITES_FROM_TOP]]
            genre_ids = [genre.id for genre in catalog.selectable_genres(session)]
            user = User(email="measure@example.invalid", password_hash="not-a-real-hash")
            session.add(user)
            session.flush()

            for _ in range(WARM_UP):
                one_request(session, rng, user.id, top_ids, genre_ids)
            samples = [
                one_request(session, rng, user.id, top_ids, genre_ids) for _ in range(args.requests)
            ]
            coverage = coverage_lines(
                session, "Whole pool", [c.title_id for c in candidates]
            ) + coverage_lines(session, f"Top {FAVORITES_FROM_TOP} by votes", top_ids)
        finally:
            connection.rollback()  # leave the database exactly as it was
    engine.dispose()

    service = [s.service_ms for s in samples]
    total = [s.total_ms for s in samples]
    warm = [s for s in samples if s.anchors]
    print(f"Recommendation baseline ({datetime.now(UTC):%Y-%m-%d %H:%M} UTC)")
    print(f"Pool: {len(candidates)} titles. Requests: {len(samples)} (+{WARM_UP} warm-up),")
    print(f"seed {args.seed}, {len(samples) - len(warm)} cold-start.")
    print()
    print("Latency, ms           p50     p95     max")
    for label, values in (("service (logged)", service), ("incl. log inserts", total)):
        print(
            f"  {label:<18}{percentile(values, 50):>6.0f}  {percentile(values, 95):>6.0f}"
            f"  {max(values):>6.0f}"
        )
    print("  target: p95 < 1500 (overview.md §7)")
    print()
    print("Results")
    print(f"  requests with < 5 results: {sum(s.results < 5 for s in samples)}")
    anchors = sum(s.anchors for s in warm)
    without = sum(s.anchors_without_neighbors for s in warm)
    print(f"  anchors with no eligible neighbor: {without} of {anchors} ({without / anchors:.0%})")
    with_reason = sum(s.neighbor_reasons > 0 for s in warm)
    print(
        f"  users with favorites shown >= 1 'Because you picked': {with_reason} of {len(warm)}"
        f" ({with_reason / len(warm):.0%})"
    )
    print()
    print("Neighbor coverage (TMDB recommendations that land in the pool)")
    for line in coverage:
        print(f"  {line}")


if __name__ == "__main__":
    main()
