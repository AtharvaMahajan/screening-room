"""Stage 0: the taste profile (recommendation-engine.md §4).

(a) Signed genre weights: each liked genre and each favorite's genres add weight.
    Avoided genres get none: they're a hard exclusion in eligibility.
(b) Anchors for favorite_neighbor: the user's favorites, capped and ordered.
"""

from collections import defaultdict

from screening_room.modules.discovery.engine.config import EngineConfig
from screening_room.modules.discovery.engine.types import Anchor, TasteProfile, UserSignals


def build_profile(signals: UserSignals, config: EngineConfig) -> TasteProfile:
    weights: dict[int, float] = defaultdict(float)
    for genre_id in signals.liked_genre_ids:
        weights[genre_id] += config.liked_genre_weight
    for favorite in signals.favorites:
        for genre_id in favorite.genre_ids:
            weights[genre_id] += config.favorite_genre_weight

    anchors = [
        Anchor(
            title_id=favorite.title_id,
            name=favorite.name,
            kind="favorite",
            weight=config.favorite_anchor_weight,
        )
        for favorite in signals.favorites
    ]
    picked_at = {favorite.title_id: favorite.picked_at for favorite in signals.favorites}
    # Deterministic: heaviest first, then most recently picked, then lowest id.
    anchors.sort(key=lambda a: a.title_id)
    anchors.sort(key=lambda a: picked_at[a.title_id], reverse=True)
    anchors.sort(key=lambda a: a.weight, reverse=True)

    return TasteProfile(
        genre_weights={g: w for g, w in sorted(weights.items()) if w != 0},
        anchors=tuple(anchors[: config.max_anchors]),
    )
