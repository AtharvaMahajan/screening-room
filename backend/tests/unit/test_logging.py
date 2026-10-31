"""Log line formats (M5b): JSON for machines, text for people, same fields."""

import json
import logging
import sys

from screening_room.core.logging import (
    JsonFormatter,
    TextFormatter,
    _OurHandler,
    configure_logging,
)


def record(msg: str = "recommendations served", **fields: object) -> logging.LogRecord:
    rec = logging.LogRecord("screening_room.x", logging.INFO, __file__, 1, msg, None, None)
    rec.context = {"request_id": "abc123def456", "user_id": 7}
    rec.fields = fields
    return rec


def test_json_lines_carry_the_request_context_and_the_fields() -> None:
    line = json.loads(JsonFormatter().format(record(latency_ms=87, cold_start=False)))

    assert line["msg"] == "recommendations served"
    assert line["level"] == "info"
    assert line["logger"] == "screening_room.x"
    assert line["ts"].endswith("+00:00")  # UTC
    assert (line["request_id"], line["user_id"]) == ("abc123def456", 7)
    assert (line["latency_ms"], line["cold_start"]) == (87, False)


def test_json_lines_include_the_exception() -> None:
    try:
        raise ValueError("boom")
    except ValueError:
        rec = record()
        rec.exc_info = sys.exc_info()

    line = json.loads(JsonFormatter().format(rec))

    assert "ValueError: boom" in line["exc"]


def test_text_lines_append_the_fields() -> None:
    line = TextFormatter().format(record(latency_ms=87))

    assert line.endswith("recommendations served request_id=abc123def456 user_id=7 latency_ms=87")


def test_configuring_twice_keeps_one_handler_and_leaves_others_alone() -> None:
    root = logging.getLogger()
    other = logging.NullHandler()
    root.addHandler(other)
    try:
        configure_logging("json", "INFO")
        configure_logging("text", "INFO")

        ours = [h for h in root.handlers if isinstance(h, _OurHandler)]
        assert len(ours) == 1
        assert isinstance(ours[0].formatter, TextFormatter)
        assert other in root.handlers
    finally:
        root.removeHandler(other)
