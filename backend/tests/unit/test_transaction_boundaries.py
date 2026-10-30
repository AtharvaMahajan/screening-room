"""Guard test for ADR-0006: only transaction owners may end a transaction.

Handlers own the transaction (project-structure.md §5.3). If a service called
`commit()`, a caller composing two services could no longer make them atomic,
and a failed commit could hide behind a 200 response.

The source is parsed with `ast` rather than searched as text, so mentions in
comments and docstrings don't count, and real calls can't hide behind formatting.
"""

import ast
from collections.abc import Iterator
from pathlib import Path, PurePosixPath

import pytest

import screening_room

SRC_ROOT = Path(screening_room.__file__).parent

# Calls that end the request's transaction.
TRANSACTION_ENDING_CALLS = {"commit", "end_read_transaction"}

# Where they're allowed (project-structure.md §5.3), relative to SRC_ROOT.
ALLOWED_LOCATIONS = [
    "modules/*/router.py",  # handlers: the transaction owners
    "modules/catalog/read_through.py",  # handler-level helper
    "modules/catalog/ingestion/**",  # CLI ingestion owns its own sessions
    "jobs.py",  # CLI entrypoint
]


def transaction_ending_calls(source: str) -> Iterator[tuple[int, str]]:
    """Yield (line, name) for each commit()/end_read_transaction() call."""
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute):
            name = func.attr  # session.commit(), db.end_read_transaction()
        elif isinstance(func, ast.Name):
            name = func.id  # end_read_transaction()
        else:
            continue
        if name in TRANSACTION_ENDING_CALLS:
            yield node.lineno, name


def is_allowed(relative_path: PurePosixPath) -> bool:
    return any(relative_path.full_match(pattern) for pattern in ALLOWED_LOCATIONS)


def test_transactions_end_only_in_allowed_locations() -> None:
    files = sorted(SRC_ROOT.rglob("*.py"))
    assert files, f"no source files found under {SRC_ROOT}"

    offenders = [
        f"{relative}:{line} {name}()"
        for path in files
        if not is_allowed(relative := PurePosixPath(path.relative_to(SRC_ROOT).as_posix()))
        for line, name in transaction_ending_calls(path.read_text(encoding="utf-8"))
    ]

    assert offenders == [], (
        "Only handlers may end a transaction (project-structure.md §5.3). "
        f"Move these into the route handler: {offenders}"
    )


# --- The guard's own building blocks, so it can't silently check nothing -------


@pytest.mark.parametrize(
    "source",
    [
        "session.commit()",
        "self.session.commit()",
        "end_read_transaction(session)",
        "db.end_read_transaction(session)",
    ],
)
def test_scanner_finds_transaction_ending_calls(source: str) -> None:
    assert len(list(transaction_ending_calls(source))) == 1


@pytest.mark.parametrize(
    "source",
    [
        "# session.commit()",
        '"""Handlers call session.commit() themselves."""',
        "session.flush()",  # services may flush
        "def end_read_transaction(session): ...",  # a definition, not a call
    ],
)
def test_scanner_ignores_non_calls(source: str) -> None:
    assert list(transaction_ending_calls(source)) == []


@pytest.mark.parametrize(
    ("path", "allowed"),
    [
        ("modules/identity/router.py", True),
        ("modules/catalog/read_through.py", True),
        ("modules/catalog/ingestion/hydrate.py", True),
        ("jobs.py", True),
        ("modules/identity/service.py", False),
        ("modules/discovery/engine/pipeline.py", False),
        ("health.py", False),
    ],
)
def test_allowed_locations(path: str, allowed: bool) -> None:
    assert is_allowed(PurePosixPath(path)) is allowed
