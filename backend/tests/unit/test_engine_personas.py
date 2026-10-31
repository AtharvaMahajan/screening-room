"""The engine against its fixture catalog and personas (recommendation-engine.md §14).

Invariants hold for every persona; persona tests check the behaviour each one
exists for; golden tests pin the exact results to ENGINE_VERSION.
"""

import random
from collections import Counter
from dataclasses import replace

import pytest

from screening_room.modules.discovery.engine import eligibility
from screening_room.modules.discovery.engine.config import ENGINE_VERSION, EngineConfig
from screening_room.modules.discovery.engine.pipeline import recommend
from screening_room.modules.discovery.engine.types import (
    PERSONAL_REASONS,
    Candidate,
    RecommendationOutcome,
)
from tests.fixtures.engine import golden
from tests.fixtures.engine.catalog import (
    AS_OF,
    GENRE_NAMES,
    GENRES,
    PERSONAS,
    PERSONAS_BY_NAME,
    SPECIAL,
    Persona,
    candidates,
    neighbor_index,
    pool_stats,
)

CANDIDATES = {c.title_id: c for c in candidates()}
CONFIG = EngineConfig()
by_name = pytest.mark.parametrize("persona", PERSONAS, ids=lambda p: p.name)


def run(persona: Persona) -> RecommendationOutcome:
    return golden.run(persona)


def candidate(title_id: int) -> Candidate:
    return CANDIDATES[title_id]


# --- Invariants: every persona -----------------------------------------------------------


@by_name
def test_results_are_never_ineligible(persona: Persona) -> None:
    given = eligibility.EligibilityInput(persona.context, persona.signals, AS_OF)

    for result in run(persona).results:
        for rule in eligibility.ELIGIBILITY_RULES:
            assert rule(candidate(result.title_id), given) is None, (result.title_id, rule.__name__)


@by_name
def test_at_most_limit_results_ranked_from_one(persona: Persona) -> None:
    results = run(persona).results

    assert len(results) <= persona.context.limit
    assert [r.rank for r in results] == list(range(1, len(results) + 1))
    assert len({r.title_id for r in results}) == len(results)  # no repeats


@by_name
def test_every_result_has_one_or_two_reasons(persona: Persona) -> None:
    for result in run(persona).results:
        assert 1 <= len(result.reasons) <= EngineConfig().max_reasons, result


@by_name
def test_personal_reasons_match_real_contributions(persona: Persona) -> None:
    """A personal reason is only allowed if its signal really added to the score (FR-10)."""
    anchor_ids = {f.title_id for f in persona.signals.favorites} | {
        r.title_id for r in persona.signals.ratings if r.stars in CONFIG.rating_anchor_weights
    }
    for result in run(persona).results:
        for reason in result.reasons:
            if reason.type == "favorite_neighbor":
                assert result.breakdown.favorite_neighbor.weighted > 0
                source = result.breakdown.neighbor_source
                assert source is not None
                assert reason.params["anchor_title_id"] == source.anchor_title_id
                assert source.anchor_title_id in anchor_ids  # a favorite or a 4-5★ rating
            elif reason.type == "genre_affinity":
                assert result.breakdown.affinity.weighted > 0
            assert reason.type in PERSONAL_REASONS or reason.type in {
                "context_genre",
                "runtime_fit",
                "well_rated",
                "pool_source",
            }


@by_name
def test_diversity_rules_hold_unless_relaxed(persona: Persona) -> None:
    outcome = run(persona)
    if outcome.diversity_relaxed:
        pytest.skip("rules were relaxed for this persona (reported)")
    config = EngineConfig()
    per_genre: Counter[int] = Counter()
    per_set: Counter[frozenset[int]] = Counter()
    for result in outcome.results:
        genres = candidate(result.title_id).genre_ids
        per_genre.update(genres - persona.context.genre_ids)
        per_set[genres] += 1

    assert all(n <= config.max_results_per_genre for n in per_genre.values()), per_genre
    assert all(n <= config.max_results_per_genre_set for n in per_set.values()), per_set
    scores = [r.score for r in outcome.results]
    assert scores == sorted(scores, reverse=True)


@by_name
@pytest.mark.parametrize("seed", [1, 2, 3])
def test_output_does_not_depend_on_input_order(persona: Persona, seed: int) -> None:
    """Shuffle candidates, every signal list, neighbor lists and dict order: same outcome (§11)."""
    shuffler = random.Random(seed)  # in the TEST only; the engine never uses randomness
    items = candidates()
    shuffler.shuffle(items)
    index_items = list(neighbor_index().items())
    shuffler.shuffle(index_items)
    shuffled_index = {k: tuple(shuffler.sample(v, len(v))) for k, v in index_items}

    def mixed[T](items: tuple[T, ...]) -> tuple[T, ...]:
        return tuple(shuffler.sample(items, len(items)))

    given = persona.signals
    signals = replace(
        given,
        favorites=mixed(given.favorites),
        ratings=mixed(given.ratings),
        watched=mixed(given.watched),
        watchlist=mixed(given.watchlist),
        not_for_me=mixed(given.not_for_me),
    )

    shuffled = recommend(
        signals,
        persona.context,
        items,
        pool_stats(items),
        shuffled_index,
        GENRE_NAMES,
        EngineConfig(),
        AS_OF,
    )

    assert shuffled.results == run(persona).results
    assert shuffled.rejected == run(persona).rejected


# --- What each persona exists to show ------------------------------------------------------


def test_new_user_is_a_cold_start_ranked_by_quality_and_popularity() -> None:
    outcome = run(PERSONAS_BY_NAME["new_user"])

    assert outcome.cold_start
    assert [n.code for n in outcome.notices] == ["cold_start"]
    assert all(r.breakdown.affinity.value == 0 for r in outcome.results)
    assert not any(reason.type in PERSONAL_REASONS for r in outcome.results for reason in r.reasons)


def test_scifi_fan_sees_because_you_picked_reasons() -> None:
    persona = PERSONAS_BY_NAME["scifi_fan"]
    outcome = run(persona)
    texts = [reason.text for r in outcome.results for reason in r.reasons]

    assert sum(text.startswith("Because you picked Space Saga") for text in texts) >= 2
    assert outcome.diagnostics.anchors_without_neighbors == 0
    favorite_ids = {f.title_id for f in persona.signals.favorites}
    assert favorite_ids.isdisjoint(
        r.title_id for r in outcome.results
    )  # never recommend a favorite


def test_favorites_without_usable_neighbors_fall_back_cleanly() -> None:
    outcome = run(PERSONAS_BY_NAME["no_usable_neighbors"])

    assert outcome.diagnostics.anchor_count == 2
    assert outcome.diagnostics.anchors_without_neighbors == 2
    assert len(outcome.results) == 5  # nothing fails; other signals rank as usual
    assert all(r.breakdown.favorite_neighbor.value == 0 for r in outcome.results)
    assert not any(
        reason.type == "favorite_neighbor" for r in outcome.results for reason in r.reasons
    )


def test_library_user_gets_rated_anchors_and_never_seen_or_dismissed_titles() -> None:
    persona = PERSONAS_BY_NAME["library_user"]
    outcome = run(persona)
    texts = [reason.text for r in outcome.results for reason in r.reasons]
    shown = {r.title_id for r in outcome.results}

    assert not outcome.cold_start  # library activity alone personalizes
    assert sum(text == "Because you rated Heist 0 5★" for text in texts) >= 2
    assert shown.isdisjoint({900, 901, 1100, 902})  # rated, watched, not for me
    rules = {r.title_id: r.rule for r in outcome.rejected}
    assert (rules[901], rules[902]) == ("watched_or_rated", "not_for_me")
    # The 1★ western pushes westerns down: none make the shortlist.
    assert not any(GENRES["western"] in candidate(t).genre_ids for t in shown)


def test_comedy_movie_under_90_minutes() -> None:
    persona = PERSONAS_BY_NAME["comedy_movie_under_90"]
    outcome = run(persona)

    for result in outcome.results:
        title = candidate(result.title_id)
        assert title.media_type == "movie"
        assert GENRES["comedy"] in title.genre_ids
        assert title.runtime_minutes is not None and title.runtime_minutes <= 90
    rejected = {r.title_id: r.rule for r in outcome.rejected}
    assert (
        rejected[SPECIAL["unknown_runtime"].title_id] == "max_runtime"
    )  # unknown counts as too long
    assert any(reason.type == "context_genre" for r in outcome.results for reason in r.reasons)


def test_tv_drama_fan_gets_only_tv() -> None:
    outcome = run(PERSONAS_BY_NAME["tv_drama_fan"])

    assert outcome.results
    assert all(candidate(r.title_id).media_type == "tv" for r in outcome.results)


def test_horror_avoider_never_sees_horror() -> None:
    outcome = run(PERSONAS_BY_NAME["horror_avoider"])

    assert all(GENRES["horror"] not in candidate(r.title_id).genre_ids for r in outcome.results)
    assert any(r.rule == "avoided_genre" for r in outcome.rejected)


def test_special_titles_are_rejected_for_the_right_reason() -> None:
    rejected = {r.title_id: r.rule for r in run(PERSONAS_BY_NAME["new_user"]).rejected}

    assert rejected[SPECIAL["unreleased"].title_id] == "unreleased"
    assert rejected[SPECIAL["adult"].title_id] == "pool_status"
    assert rejected[SPECIAL["summary_only"].title_id] == "pool_status"
    assert rejected[SPECIAL["missing"].title_id] == "pool_status"


# --- Golden: exact results, changed only with an ENGINE_VERSION bump ---------------------------


def test_golden_file_matches_engine_version() -> None:
    assert golden.load()["engine_version"] == ENGINE_VERSION, (
        "Golden expectations were recorded for another engine version"
    )


@by_name
def test_golden_results(persona: Persona) -> None:
    expected = golden.expected_results(persona.name)

    actual = golden.actual_results(persona)

    assert actual == expected, (
        "Engine output changed. If intended: bump ENGINE_VERSION and run "
        "`python -m tests.fixtures.engine.golden --update`, then review the diff."
    )
