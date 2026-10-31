"""The recommendation service: retrieval -> pure engine -> logged results.

The I/O shell around engine/ (recommendation-engine.md §2). It reads the clock
once, so the engine never does, and stages the request and its results for the
handler's single commit (overview.md §6.1). Reads only the local database.
"""

import time
from dataclasses import asdict
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from screening_room.core.errors import AppError
from screening_room.modules.catalog import service as catalog
from screening_room.modules.discovery.engine.config import (
    ENGINE_VERSION,
    EngineConfig,
    config_hash,
)
from screening_room.modules.discovery.engine.pipeline import recommend
from screening_room.modules.discovery.engine.types import (
    Reason,
    RecommendationContext,
    RecommendationOutcome,
)
from screening_room.modules.discovery.models import RecRequest, RecResult, RecResultEvent
from screening_room.modules.discovery.retrieval import retrieve
from screening_room.modules.discovery.schemas import (
    NoticeOut,
    ReasonOut,
    RecommendationOut,
    RecommendationRequestIn,
    RecommendationsOut,
    ResultEventIn,
)
from screening_room.modules.library import service as library

ENGINE_CONFIG = EngineConfig()
CONFIG_HASH = config_hash(ENGINE_CONFIG)


def recommend_for_user(
    session: Session,
    user_id: int,
    body: RecommendationRequestIn,
    image_base_url: str,
    *,
    as_of: date | None = None,  # tests pin it; otherwise today's date in UTC
) -> RecommendationsOut:
    """Build a shortlist and stage its log rows. The caller commits."""
    context = _context(session, body)
    as_of = as_of or datetime.now(UTC).date()

    started = time.perf_counter()
    inputs = retrieve(session, user_id, ENGINE_CONFIG)
    outcome = recommend(
        inputs.signals,
        context,
        inputs.candidates,
        inputs.pool_stats,
        inputs.neighbor_index,
        inputs.genre_names,
        ENGINE_CONFIG,
        as_of,
    )
    latency_ms = round((time.perf_counter() - started) * 1000)

    request, rows = _log(
        session, user_id, context, outcome, inputs.pool_stats.pool_size, latency_ms
    )
    previews = catalog.title_previews(
        session, (r.title_id for r in outcome.results), image_base_url
    )
    return RecommendationsOut(
        request_id=request.id,
        cold_start=outcome.cold_start,
        notices=[NoticeOut.model_validate(asdict(notice)) for notice in outcome.notices],
        results=[
            RecommendationOut(
                result_id=row.id,
                rank=result.rank,
                title=previews[result.title_id],
                reasons=[_reason_out(reason) for reason in result.reasons],
            )
            for result, row in zip(outcome.results, rows, strict=True)
        ],
    )


def _context(session: Session, body: RecommendationRequestIn) -> RecommendationContext:
    genre_ids = frozenset(body.genre_ids)
    selectable = {genre.id for genre in catalog.selectable_genres(session)}
    if unknown := genre_ids - selectable:
        raise AppError(422, "unknown_genre", f"Unknown genre ids: {sorted(unknown)}.")
    return RecommendationContext(
        media_type=body.media_type,
        genre_ids=genre_ids,
        max_runtime_minutes=body.max_runtime_minutes,
        exclude_title_ids=frozenset(body.exclude_title_ids),
        limit=body.limit,
    )


def _reason_out(reason: Reason) -> ReasonOut:
    anchor = reason.params.get("anchor_title_id")
    return ReasonOut(
        type=reason.type,
        text=reason.text,
        anchor_title_id=anchor if isinstance(anchor, int) else None,
    )


def _log(
    session: Session,
    user_id: int,
    context: RecommendationContext,
    outcome: RecommendationOutcome,
    pool_size: int,
    latency_ms: int,
) -> tuple[RecRequest, list[RecResult]]:
    """Stage the request and its results (recommendation-engine.md §13); flush for ids."""
    diagnostics = outcome.diagnostics
    request = RecRequest(
        user_id=user_id,
        context={
            "media_type": context.media_type,
            "genre_ids": sorted(context.genre_ids),
            "max_runtime_minutes": context.max_runtime_minutes,
            # Only the count: the ids themselves say little and could be long.
            "excluded_count": len(context.exclude_title_ids),
            "limit": context.limit,
        },
        engine_version=ENGINE_VERSION,
        config_hash=CONFIG_HASH,
        pool_size=pool_size,
        candidate_count=diagnostics.candidate_count,
        eligible_count=diagnostics.eligible_count,
        anchor_count=diagnostics.anchor_count,
        anchors_without_neighbors=diagnostics.anchors_without_neighbors,
        cold_start=outcome.cold_start,
        diversity_relaxed=outcome.diversity_relaxed,
        latency_ms=latency_ms,
    )
    session.add(request)
    session.flush()  # assigns request.id
    rows = [
        RecResult(
            request_id=request.id,
            title_id=result.title_id,
            rank=result.rank,
            score=result.score,
            score_breakdown=asdict(result.breakdown),
            # Exactly what the user is shown.
            reasons=[_reason_out(r).model_dump() for r in result.reasons],
        )
        for result in outcome.results
    ]
    session.add_all(rows)
    session.flush()  # assigns each result's id
    return request, rows


def record_result_event(
    session: Session, user_id: int, result_id: int, event: ResultEventIn
) -> int:
    """Apply what the user did with a recommendation, and log it. Returns the title id.

    The library change carries the result id (attribution, overview.md §6.4), and
    both are staged for the handler's single commit: if the library rejects the
    action (e.g. a future watch date), no event is logged either.
    """
    title_id = session.scalar(
        select(RecResult.title_id)
        .join(RecRequest, RecRequest.id == RecResult.request_id)
        .where(RecResult.id == result_id, RecRequest.user_id == user_id)
    )
    if title_id is None:  # missing, or another user's: same answer, no leak
        raise AppError(404, "result_not_found", "There's no such recommendation.")

    match event.type:
        case "saved":
            library.add_to_watchlist(session, user_id, title_id, rec_result_id=result_id)
        case "watched":
            library.mark_watched(
                session, user_id, title_id, event.watched_on, rec_result_id=result_id
            )
        case "rated":
            assert event.rating is not None  # the schema requires it
            library.rate(session, user_id, title_id, event.rating, rec_result_id=result_id)
        case "not_for_me":
            library.mark_not_for_me(session, user_id, title_id, rec_result_id=result_id)
        case "opened" | "skipped":
            pass  # logged only
    session.add(RecResultEvent(result_id=result_id, event_type=event.type))
    return title_id
