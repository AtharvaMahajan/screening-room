"""Every weight, threshold, cap and prior in one place (recommendation-engine.md §12).

These are *initial values*: tunable, but only together with the golden tests.
Bump ENGINE_VERSION whenever scoring behaviour changes on purpose, and update
the golden expectations in the same commit.
"""

import hashlib
import json

from pydantic import BaseModel, ConfigDict

ENGINE_VERSION = "1.0.1"  # 1.0.1: genre_affinity wording only; rankings unchanged


class EngineConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    # --- Scoring weights (§7): sum to 1 ---
    weight_affinity: float = 0.45
    weight_favorite_neighbor: float = 0.25
    weight_quality: float = 0.20
    weight_popularity: float = 0.10

    # --- Taste profile (§4) ---
    liked_genre_weight: float = 1.0  # per liked genre
    favorite_genre_weight: float = 1.0  # to each genre of each favorite
    favorite_anchor_weight: float = 1.0
    max_anchors: int = 30

    # --- favorite_neighbor (§7.1): rank 1 -> 1.0 ... rank 20 -> 0.05 ---
    neighbor_rank_span: int = 20

    # --- quality (§7): Bayesian average with this many "prior" votes ---
    quality_prior_votes: int = 500

    # --- Diversity (§8) ---
    max_results_per_genre: int = 3
    max_results_per_genre_set: int = 1

    # --- Explanations (§9) ---
    max_reasons: int = 2
    min_neighbor_contribution: float = 0.08
    min_affinity_contribution: float = 0.10
    min_quality_for_well_rated: float = 0.75


def config_hash(config: EngineConfig) -> str:
    """A short, stable fingerprint of the config, stored with every request (§12)."""
    serialized = json.dumps(config.model_dump(), sort_keys=True)
    return hashlib.sha256(serialized.encode()).hexdigest()[:16]
