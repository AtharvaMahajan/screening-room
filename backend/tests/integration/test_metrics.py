"""Recommendation metrics from the request, result and event logs (M5b).

Starts from an EMPTY catalog, which also clears every logged request, so the
window holds exactly what this test creates.
"""

from datetime import UTC, date, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from screening_room.jobs import build_parser
from screening_room.modules.discovery.metrics import format_report, recommendation_metrics
from tests.integration.helpers import add_candidate, genre_id, register, send


def test_metrics_count_requests_latency_and_outcomes(
    client: TestClient, db_session: Session, empty_catalog: None
) -> None:
    for name in ("Metric A", "Metric B", "Metric C"):
        add_candidate(db_session, name, release_date=date(2016, 1, 1))  # all Drama
    token = register(client, email="metrics@example.com").json()["csrf_token"]

    def call(method: str, path: str, body: object = None) -> dict[str, object]:
        response = send(client, method, path, body, csrf_token=token)
        assert response.status_code < 300, response.text
        result: dict[str, object] = response.json()
        return result

    # 1: a cold start, and a short list (3 titles, 5 asked for).
    first = call("POST", "/api/recommendations", {"limit": 5})["results"]
    assert isinstance(first, list)
    saved, dismissed = first[0]["result_id"], first[1]["result_id"]
    for event, result_id in (("saved", saved), ("opened", saved), ("opened", saved)):
        call("POST", f"/api/recommendations/results/{result_id}/events", {"type": event})
    call("POST", f"/api/recommendations/results/{dismissed}/events", {"type": "not_for_me"})
    # 2 and 3: personalized now (a liked genre), and short again (one title dismissed).
    # Two of these, so 1 cold start of 3 isn't the same count either way round.
    call("PUT", "/api/me/preferences", {"liked_genre_ids": [genre_id(db_session, "drama")]})
    call("POST", "/api/recommendations", {"limit": 5})
    call("POST", "/api/recommendations", {"limit": 3})

    report = recommendation_metrics(db_session, datetime.now(UTC) - timedelta(hours=1))

    assert (report.requests, report.cold_start, report.short_lists) == (3, 1, 3)
    assert report.results_shown == 7  # 3, then 2 and 2
    assert report.latency_p95_ms is not None and report.latency_max_ms is not None
    assert {k: v for k, v in report.results_with.items() if v} == {
        "saved": 1,
        "opened": 1,  # distinct results, not events
        "not_for_me": 1,
    }
    by_reason = {row.reason: row for row in report.by_main_reason}
    assert sum(row.shown for row in by_reason.values()) == 7
    assert by_reason["genre_affinity"].shown == 4  # the two personalized requests
    assert sum(row.saved for row in by_reason.values()) == 1
    assert sum(row.not_for_me for row in by_reason.values()) == 1
    text = format_report(report)
    assert "requests: 3" in text and "cold start: 1 (33%)" in text


def test_an_empty_window_reports_zeros(db_session: Session, empty_catalog: None) -> None:
    report = recommendation_metrics(db_session, datetime.now(UTC) - timedelta(days=1))

    assert (report.requests, report.results_shown, report.latency_p95_ms) == (0, 0, None)
    assert "latency: p50 -, p95 -" in format_report(report)


def test_the_metrics_command_takes_a_window_in_days() -> None:
    assert build_parser().parse_args(["metrics", "--days", "3"]).days == 3
    assert build_parser().parse_args(["metrics"]).days == 7
