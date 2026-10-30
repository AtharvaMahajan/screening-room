"""Constraint and index names must fit PostgreSQL's 63-character identifier limit.

SQLAlchemy shortens longer names with a hash suffix (e.g. "..._media_1fe5"), which
makes database errors and future migrations hard to read. Give such constraints
an explicit name instead.
"""

import screening_room.modules.catalog.models
import screening_room.modules.identity.models  # noqa: F401  (registers the tables)
from screening_room.db import Base

POSTGRES_MAX_IDENTIFIER_LENGTH = 63


def test_every_constraint_and_index_name_fits_postgres() -> None:
    tables = Base.metadata.tables.values()
    constraint_names = [str(c.name) for t in tables for c in t.constraints if c.name]
    index_names = [str(i.name) for t in tables for i in t.indexes if i.name]
    names = constraint_names + index_names
    assert names, "expected some constraints to check"

    too_long = [name for name in names if len(name) > POSTGRES_MAX_IDENTIFIER_LENGTH]

    assert too_long == [], f"name these explicitly (max 63 characters): {too_long}"
