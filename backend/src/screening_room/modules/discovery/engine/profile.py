"""Stage 0: the taste profile (recommendation-engine.md §4).

(a) Signed genre weights: liked genres, and each title the user picked, rated,
    watched, saved or turned down adds its weight to every genre of that title.
    Avoided genres get none: they're a hard exclusion in eligibility.
(b) Anchors for favorite_neighbor: favorites and 4-5★ ratings, capped and ordered.
"""

from collections import defaultdict
from collections.abc import Iterable
from datetime import datetime

from screening_room.modules.discovery.engine.config import EngineConfig
from screening_room.modules.discovery.engine.types import Anchor, TasteProfile, UserSignals


def build_profile(signals: UserSignals, config: EngineConfig) -> TasteProfile:
    weights: dict[int, float] = defaultdict(float)

    def add(genre_ids: Iterable[int], weight: float) -> None:
        for genre_id in genre_ids:
            weights[genre_id] += weight

    add(signals.liked_genre_ids, config.liked_genre_weight)
    for favorite in signals.favorites:
        add(favorite.genre_ids, config.favorite_genre_weight)
    rated_ids = {rating.title_id for rating in signals.ratings}
    for rating in signals.ratings:
        add(rating.genre_ids, config.rating_genre_weights[rating.stars])
    for title in signals.watched:
        if title.title_id not in rated_ids:  # a rating says more than "watched"
            add(title.genre_ids, config.watched_genre_weight)
    for title in signals.watchlist:
        add(title.genre_ids, config.watchlist_genre_weight)
    for title in signals.not_for_me:
        add(title.genre_ids, config.not_for_me_genre_weight)

    return TasteProfile(
        genre_weights={g: w for g, w in sorted(weights.items()) if round(w, 9) != 0},
        anchors=_anchors(signals, config),
    )


def _anchors(signals: UserSignals, config: EngineConfig) -> tuple[Anchor, ...]:
    """Favorites and well-rated titles, heaviest first, then newest, then lowest id.

    A title that's both a favorite and rated counts once, with its heavier weight.
    """
    candidates: list[tuple[Anchor, datetime]] = [
        (
            Anchor(f.title_id, f.name, kind="favorite", weight=config.favorite_anchor_weight),
            f.picked_at,
        )
        for f in signals.favorites
    ]
    candidates += [
        (
            Anchor(
                r.title_id,
                r.name,
                kind="rated",
                weight=config.rating_anchor_weights[r.stars],
                stars=r.stars,
            ),
            r.rated_at,
        )
        for r in signals.ratings
        if r.stars in config.rating_anchor_weights
    ]
    # Three stable sorts, least important key first.
    candidates.sort(key=lambda pair: pair[0].title_id)
    candidates.sort(key=lambda pair: pair[1], reverse=True)
    candidates.sort(key=lambda pair: pair[0].weight, reverse=True)

    anchors: list[Anchor] = []
    seen: set[int] = set()
    for anchor, _ in candidates:
        if anchor.title_id not in seen:  # the first is the heaviest (then newest)
            seen.add(anchor.title_id)
            anchors.append(anchor)
    return tuple(anchors[: config.max_anchors])
