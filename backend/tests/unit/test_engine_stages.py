"""Each engine stage on its own (recommendation-engine.md §4-§9)."""

import math
from dataclasses import replace
from datetime import UTC, date, datetime
from typing import Any

import pytest

from screening_room.modules.discovery.engine import eligibility, ranking, scoring
from screening_room.modules.discovery.engine.config import EngineConfig, config_hash
from screening_room.modules.discovery.engine.explain import explain, format_runtime
from screening_room.modules.discovery.engine.profile import build_profile
from screening_room.modules.discovery.engine.types import (
    Anchor,
    Candidate,
    Favorite,
    Neighbor,
    NeighborSource,
    PoolStats,
    RecommendationContext,
    ScoreBreakdown,
    ScoredCandidate,
    SignalScore,
    TasteProfile,
    UserSignals,
)

CONFIG = EngineConfig()
AS_OF = date(2026, 6, 1)
STATS = PoolStats(mean_vote_average=7.0, max_popularity=100.0, pool_size=10)
NAMES = {1: "Action", 2: "Comedy", 3: "Drama", 4: "Horror"}


def make(title_id: int = 1, **overrides: Any) -> Candidate:
    base = Candidate(
        title_id=title_id,
        media_type="movie",
        genre_ids=frozenset({3}),
        runtime_minutes=100,
        release_date=date(2010, 1, 1),
        vote_average=7.0,
        vote_count=1000,
        popularity=10.0,
        source_keys=frozenset({"movie:top_rated"}),
    )
    return replace(base, **overrides)


def fav(title_id: int, day: int, genres: frozenset[int] = frozenset({3})) -> Favorite:
    return Favorite(title_id, f"Fav {title_id}", genres, datetime(2026, 5, day, tzinfo=UTC))


# --- Profile ---------------------------------------------------------------------------------


def test_profile_adds_liked_genres_and_favorite_genres() -> None:
    profile = build_profile(
        UserSignals(liked_genre_ids=frozenset({3}), favorites=(fav(10, 1, frozenset({3, 1})),)),
        CONFIG,
    )

    assert profile.genre_weights == {1: 1.0, 3: 2.0}


def test_avoided_genres_get_no_weight() -> None:
    profile = build_profile(UserSignals(avoided_genre_ids=frozenset({4})), CONFIG)

    assert profile.genre_weights == {}
    assert profile.is_empty


def test_anchors_newest_first_then_lowest_id_and_capped() -> None:
    favorites = (fav(30, 1), fav(20, 3), fav(10, 3))
    profile = build_profile(
        UserSignals(favorites=favorites), CONFIG.model_copy(update={"max_anchors": 2})
    )

    assert [a.title_id for a in profile.anchors] == [10, 20]  # day 3 before day 1; tie -> lower id


# --- Eligibility ------------------------------------------------------------------------------


def check(
    c: Candidate,
    context: RecommendationContext | None = None,
    signals: UserSignals | None = None,
) -> str | None:
    given = eligibility.EligibilityInput(
        context or RecommendationContext(), signals or UserSignals(), AS_OF
    )
    _, rejected = eligibility.check([c], given)
    return rejected[0].rule if rejected else None


@pytest.mark.parametrize(
    ("c", "context", "signals", "rule"),
    [
        (
            make(media_type="tv", runtime_minutes=None),
            RecommendationContext(media_type="movie"),
            UserSignals(),
            "media_type",
        ),
        (make(), RecommendationContext(genre_ids=frozenset({2})), UserSignals(), "context_genres"),
        (
            make(runtime_minutes=130),
            RecommendationContext(max_runtime_minutes=120),
            UserSignals(),
            "max_runtime",
        ),
        (
            make(runtime_minutes=None),
            RecommendationContext(max_runtime_minutes=120),
            UserSignals(),
            "max_runtime",
        ),
        (make(), None, UserSignals(avoided_genre_ids=frozenset({3})), "avoided_genre"),
        (make(title_id=10), None, UserSignals(favorites=(fav(10, 1),)), "favorite"),
        (
            make(title_id=5),
            RecommendationContext(exclude_title_ids=frozenset({5})),
            UserSignals(),
            "explicit_exclusion",
        ),
        (make(release_date=date(2026, 6, 2)), None, UserSignals(), "unreleased"),
        (make(release_date=None), None, UserSignals(), "unreleased"),
        (make(adult=True), None, UserSignals(), "pool_status"),
        (make(detail_level="summary"), None, UserSignals(), "pool_status"),
    ],
)
def test_each_eligibility_rule(
    c: Candidate, context: RecommendationContext | None, signals: UserSignals, rule: str
) -> None:
    assert check(c, context, signals) == rule


def test_runtime_limit_ignores_tv_and_exact_limit_passes() -> None:
    limit = RecommendationContext(max_runtime_minutes=120)

    assert check(make(media_type="tv", runtime_minutes=None), limit) is None  # R4
    assert check(make(runtime_minutes=120), limit) is None
    assert check(make(release_date=AS_OF)) is None  # released today counts


# --- Scoring -------------------------------------------------------------------------------


def test_affinity_is_cosine_similarity() -> None:
    weights = {3: 1.0, 2: 1.0}

    assert scoring.affinity(make(genre_ids=frozenset({3})), weights) == pytest.approx(
        1 / math.sqrt(2)
    )
    assert scoring.affinity(make(genre_ids=frozenset({3, 2})), weights) == pytest.approx(1.0)
    assert scoring.affinity(make(genre_ids=frozenset({4})), weights) == 0.0
    assert scoring.affinity(make(), {}) == 0.0  # cold start
    assert scoring.affinity(make(genre_ids=frozenset({3})), {3: -1.0}) == pytest.approx(-1.0)


def test_quality_is_a_bayesian_average() -> None:
    # Few votes pull towards the pool mean (7.0); many votes keep the title's own 9.0.
    few = scoring.quality(make(vote_average=9.0, vote_count=10), STATS, CONFIG)
    many = scoring.quality(make(vote_average=9.0, vote_count=100_000), STATS, CONFIG)

    assert few == pytest.approx(((10 / 510) * 9.0 + (500 / 510) * 7.0) / 10)
    assert 0.70 < few < many < 0.90


def test_popularity_is_log_scaled_to_the_pool_maximum() -> None:
    assert scoring.popularity(make(popularity=100.0), STATS) == pytest.approx(1.0)
    assert scoring.popularity(make(popularity=None), STATS) == 0.0
    assert 0 < scoring.popularity(make(popularity=10.0), STATS) < 1


def test_favorite_neighbor_decays_with_rank_and_breaks_ties() -> None:
    anchors = [Anchor(10, "Ten", "favorite", 1.0), Anchor(20, "Twenty", "favorite", 1.0)]
    index = {
        10: (Neighbor(1, 1), Neighbor(2, 20)),
        20: (Neighbor(1, 1), Neighbor(3, 5), Neighbor(99, 1)),  # 99 isn't eligible
    }

    best = scoring.best_neighbor_sources(anchors, index, frozenset({1, 2, 3}), CONFIG)

    assert best[1][0] == 1.0 and best[1][1].anchor_title_id == 10  # tie: lower anchor id
    assert best[2][0] == pytest.approx(0.05)  # rank 20
    assert best[3][0] == pytest.approx(0.8)  # rank 5
    assert 99 not in best


# --- Ranking and diversity ------------------------------------------------------------------


def scored(title_id: int, score: float, genres: set[int]) -> ScoredCandidate:
    zero = SignalScore(0.0, 0.0)
    return ScoredCandidate(
        make(title_id, genre_ids=frozenset(genres)),
        ScoreBreakdown(SignalScore(score, score), zero, zero, zero, None),
    )


def test_ranking_caps_each_genre_at_three() -> None:
    items = [scored(i, 1 - i / 10, {3, i}) for i in range(1, 5)] + [scored(9, 0.1, {1})]

    chosen, relaxed = ranking.rank(items, RecommendationContext(), CONFIG)

    assert [c.candidate.title_id for c in chosen] == [1, 2, 3, 9, 4]  # 4th drama waits
    assert relaxed  # the 5th slot could only be filled by breaking the cap


def test_requested_genres_are_exempt_from_the_cap() -> None:
    items = [scored(i, 1 - i / 10, {3, 10 + i}) for i in range(1, 6)]

    chosen, relaxed = ranking.rank(items, RecommendationContext(genre_ids=frozenset({3})), CONFIG)

    assert len(chosen) == 5 and not relaxed


def test_identical_genre_sets_count_as_near_duplicates() -> None:
    items = [scored(1, 0.9, {3}), scored(2, 0.8, {3}), scored(3, 0.1, {1})]

    chosen, _ = ranking.rank(items, RecommendationContext(limit=2), CONFIG)

    assert [c.candidate.title_id for c in chosen] == [1, 3]


def test_equal_scores_are_ordered_by_title_id() -> None:
    items = [scored(7, 0.5, {1}), scored(3, 0.5, {2})]

    assert [s.candidate.title_id for s in ranking.ordered(items)] == [3, 7]


# --- Explanations -----------------------------------------------------------------------------


def explained(
    item: ScoredCandidate,
    profile: TasteProfile,
    context: RecommendationContext | None = None,
) -> list[str]:
    return [
        r.type for r in explain(item, profile, context or RecommendationContext(), NAMES, CONFIG)
    ]


def breakdown_with(
    *, affinity: float = 0.0, neighbor: float = 0.0, quality: float = 0.5
) -> ScoreBreakdown:
    source = NeighborSource(10, "Ten", "favorite", 1) if neighbor else None
    return ScoreBreakdown(
        SignalScore(affinity / 0.45, affinity),
        SignalScore(neighbor / 0.25, neighbor),
        SignalScore(quality, quality * 0.2),
        SignalScore(0.0, 0.0),
        source,
    )


LIKES_DRAMA = TasteProfile(genre_weights={3: 1.0}, anchors=())


def test_favorite_link_is_preferred_over_genres_when_both_qualify() -> None:
    item = ScoredCandidate(make(), breakdown_with(affinity=0.40, neighbor=0.20))

    assert explained(item, LIKES_DRAMA)[0] == "favorite_neighbor"


def test_weak_signals_produce_no_personal_reason() -> None:
    item = ScoredCandidate(make(), breakdown_with(affinity=0.05, neighbor=0.05))

    assert explained(item, LIKES_DRAMA) == ["pool_source"]


def test_context_and_quality_reasons_fill_in() -> None:
    item = ScoredCandidate(make(), breakdown_with(quality=0.8))
    context = RecommendationContext(genre_ids=frozenset({3}), max_runtime_minutes=120)

    assert explained(item, TasteProfile({}, ()), context) == ["context_genre", "runtime_fit"]


def test_pool_source_reason_text_follows_the_source() -> None:
    tv_popular = ScoredCandidate(
        make(media_type="tv", source_keys=frozenset({"tv:popular"})), breakdown_with()
    )

    reasons = explain(tv_popular, TasteProfile({}, ()), RecommendationContext(), NAMES, CONFIG)

    assert [r.text for r in reasons] == ["Popular on TMDB"]


@pytest.mark.parametrize(("minutes", "text"), [(116, "1h 56m"), (45, "45m"), (120, "2h")])
def test_format_runtime(minutes: int, text: str) -> None:
    assert format_runtime(minutes) == text


# --- Config ----------------------------------------------------------------------------------


def test_config_hash_is_stable_and_changes_with_any_value() -> None:
    assert config_hash(EngineConfig()) == config_hash(EngineConfig())
    assert config_hash(EngineConfig()) != config_hash(EngineConfig(weight_quality=0.21))


def test_scoring_weights_sum_to_one() -> None:
    weights = (
        CONFIG.weight_affinity
        + CONFIG.weight_favorite_neighbor
        + CONFIG.weight_quality
        + CONFIG.weight_popularity
    )
    assert weights == pytest.approx(1.0)
