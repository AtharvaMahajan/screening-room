"""Golden expectations: each persona's top results, checked into the repo.

They change only with an ENGINE_VERSION bump (recommendation-engine.md §12).
After an intentional behaviour change:

    uv run python -m tests.fixtures.engine.golden --update

then review the diff of golden.json and bump ENGINE_VERSION in the same commit.
"""

import json
import sys
from pathlib import Path
from typing import Any

from screening_room.modules.discovery.engine.config import ENGINE_VERSION, EngineConfig
from screening_room.modules.discovery.engine.pipeline import recommend
from screening_room.modules.discovery.engine.types import RecommendationOutcome
from tests.fixtures.engine.catalog import (
    AS_OF,
    GENRE_NAMES,
    PERSONAS,
    Persona,
    candidates,
    neighbor_index,
    pool_stats,
)

GOLDEN_FILE = Path(__file__).with_name("golden.json")


def run(persona: Persona) -> RecommendationOutcome:
    items = candidates()
    return recommend(
        persona.signals,
        persona.context,
        items,
        pool_stats(items),
        neighbor_index(),
        GENRE_NAMES,
        EngineConfig(),
        AS_OF,
    )


def current() -> dict[str, Any]:
    return {
        "engine_version": ENGINE_VERSION,
        "personas": {persona.name: actual_results(persona) for persona in PERSONAS},
    }


def load() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(GOLDEN_FILE.read_text(encoding="utf-8"))
    return data


def expected_results(persona_name: str) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = load()["personas"][persona_name]
    return results


def actual_results(persona: Persona) -> list[dict[str, Any]]:
    return [
        {"title_id": r.title_id, "reasons": [reason.type for reason in r.reasons]}
        for r in run(persona).results
    ]


if __name__ == "__main__":
    if sys.argv[1:] != ["--update"]:
        sys.exit("usage: python -m tests.fixtures.engine.golden --update")
    GOLDEN_FILE.write_text(json.dumps(current(), indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {GOLDEN_FILE.name} for engine {ENGINE_VERSION}: review the diff")
