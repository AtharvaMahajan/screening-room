"""The engine core must be pure (recommendation-engine.md §11, ADR-0010).

No database, network, environment, randomness or clock inside engine/, so the
same inputs always give the same output and every stage is testable alone.
Checked by reading the source, so it can't silently pass.
"""

import ast
from pathlib import Path

import pytest

import screening_room.modules.discovery.engine as engine_package

ENGINE_DIR = Path(engine_package.__file__).parent
ENGINE_FILES = sorted(ENGINE_DIR.glob("*.py"))

# Randomness, environment and clock:
_NONDETERMINISTIC = {"random", "secrets", "os", "time", "uuid"}
# Database, network, web framework, and settings read from the environment:
_IO = {"sqlalchemy", "psycopg", "httpx2", "fastapi", "screening_room.db", "screening_room.config"}
FORBIDDEN_MODULES = _NONDETERMINISTIC | _IO
FORBIDDEN_CALLS = {"now", "today", "utcnow"}  # datetime.now(), date.today()...


def imported_modules(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_the_engine_has_source_files() -> None:
    assert len(ENGINE_FILES) >= 7, ENGINE_FILES  # guard against checking nothing


@pytest.mark.parametrize("path", ENGINE_FILES, ids=lambda p: p.name)
def test_engine_file_is_pure(path: Path) -> None:
    tree = ast.parse(path.read_text(encoding="utf-8"))

    bad_imports = {
        name
        for name in imported_modules(tree)
        if any(name == f or name.startswith(f"{f}.") for f in FORBIDDEN_MODULES)
        or (
            name.startswith("screening_room.")
            and not name.startswith("screening_room.modules.discovery.engine")
        )
    }
    clock_calls = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in FORBIDDEN_CALLS
    }

    assert bad_imports == set(), f"{path.name} imports {bad_imports}"
    assert clock_calls == set(), f"{path.name} reads the clock: {clock_calls}"
