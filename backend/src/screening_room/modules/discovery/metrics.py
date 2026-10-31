"""Recommendation metrics from the logs we already keep (recommendation-engine.md §13).

No metrics server (ADR-0002): rec_requests, rec_results and rec_result_events
hold everything, so these are plain SQL reports over a time window.
Run with `python -m screening_room.jobs metrics --days 7`.
"""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Integer, case, distinct, func, select
from sqlalchemy.orm import Session

from screening_room.modules.discovery.models import (
    EVENT_TYPES,
    RecRequest,
    RecResult,
    RecResultEvent,
)


@dataclass(frozen=True)
class SignalOutcomes:
    """Results grouped by their first (main) reason, e.g. favorite_neighbor."""

    reason: str
    shown: int
    saved: int
    not_for_me: int


@dataclass(frozen=True)
class MetricsReport:
    since: datetime
    requests: int
    latency_p50_ms: float | None
    latency_p95_ms: float | None
    latency_max_ms: int | None
    cold_start: int
    short_lists: int  # fewer results than asked for
    anchors: int
    anchors_without_neighbors: int
    results_shown: int
    results_with: dict[str, int]  # event type -> results with at least one
    by_main_reason: list[SignalOutcomes]


def recommendation_metrics(session: Session, since: datetime) -> MetricsReport:
    in_window = RecRequest.created_at >= since
    shown_per_request = (
        select(RecResult.request_id, func.count().label("shown"))
        .group_by(RecResult.request_id)
        .subquery()
    )
    asked = RecRequest.context["limit"].as_integer()
    totals = session.execute(
        select(
            func.count(RecRequest.id),
            func.percentile_cont(0.5).within_group(RecRequest.latency_ms),
            func.percentile_cont(0.95).within_group(RecRequest.latency_ms),
            func.max(RecRequest.latency_ms),
            func.count().filter(RecRequest.cold_start),
            func.count().filter(func.coalesce(shown_per_request.c.shown, 0) < asked),
            func.coalesce(func.sum(RecRequest.anchor_count), 0),
            func.coalesce(func.sum(RecRequest.anchors_without_neighbors), 0),
        )
        .outerjoin(shown_per_request, shown_per_request.c.request_id == RecRequest.id)
        .where(in_window)
    ).one()

    results_in_window = select(RecResult.id).join(RecRequest).where(in_window)
    results_shown = session.scalar(select(func.count()).select_from(results_in_window.subquery()))
    with_event = dict(
        session.execute(
            select(RecResultEvent.event_type, func.count(distinct(RecResultEvent.result_id)))
            .where(RecResultEvent.result_id.in_(results_in_window))
            .group_by(RecResultEvent.event_type)
        ).all()
    )

    main_reason = RecResult.reasons[0]["type"].as_string()
    had = (
        select(
            RecResultEvent.result_id,
            func.max(case((RecResultEvent.event_type == "saved", 1), else_=0)).label("saved"),
            func.max(case((RecResultEvent.event_type == "not_for_me", 1), else_=0)).label(
                "not_for_me"
            ),
        )
        .group_by(RecResultEvent.result_id)
        .subquery()
    )
    by_reason = session.execute(
        select(
            main_reason,
            func.count(RecResult.id),
            func.coalesce(func.sum(had.c.saved.cast(Integer)), 0),
            func.coalesce(func.sum(had.c.not_for_me.cast(Integer)), 0),
        )
        .join(RecRequest)
        .outerjoin(had, had.c.result_id == RecResult.id)
        .where(in_window)
        .group_by(main_reason)
        .order_by(func.count(RecResult.id).desc(), main_reason)
    ).all()

    requests, p50, p95, latency_max, cold, short, anchors, without = totals
    return MetricsReport(
        since=since,
        requests=requests,
        latency_p50_ms=p50,
        latency_p95_ms=p95,
        latency_max_ms=latency_max,
        cold_start=cold,
        short_lists=short,
        anchors=anchors,
        anchors_without_neighbors=without,
        results_shown=results_shown or 0,
        results_with={event: with_event.get(event, 0) for event in EVENT_TYPES},
        by_main_reason=[SignalOutcomes(*row) for row in by_reason],
    )


def format_report(report: MetricsReport) -> str:
    def share(part: int, whole: int) -> str:
        return f"{part / whole:.0%}" if whole else "-"

    def ms(value: float | None) -> str:
        return f"{value:.0f} ms" if value is not None else "-"

    lines = [
        f"Recommendations since {report.since:%Y-%m-%d %H:%M} UTC",
        f"  requests: {report.requests}",
        f"  latency: p50 {ms(report.latency_p50_ms)}, p95 {ms(report.latency_p95_ms)}, "
        f"max {ms(report.latency_max_ms)} (target p95 < 1500 ms)",
        f"  cold start: {report.cold_start} ({share(report.cold_start, report.requests)})",
        f"  fewer results than asked: {report.short_lists} "
        f"({share(report.short_lists, report.requests)})",
        f"  anchors with no eligible neighbor: {report.anchors_without_neighbors} of "
        f"{report.anchors} ({share(report.anchors_without_neighbors, report.anchors)})",
        "",
        f"Results shown: {report.results_shown}. Share with at least one...",
    ]
    lines += [
        f"  {event:<11} {count:>5} ({share(count, report.results_shown)})"
        for event, count in report.results_with.items()
    ]
    lines += ["", "By main reason (first reason shown)       shown   saved   not for me"]
    lines += [
        f"  {row.reason:<38} {row.shown:>6}  {share(row.saved, row.shown):>6}  "
        f"{share(row.not_for_me, row.shown):>10}"
        for row in report.by_main_reason
    ]
    return "\n".join(lines)
