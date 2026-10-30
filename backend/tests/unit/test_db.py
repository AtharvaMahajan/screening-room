"""db.py behaviour that doesn't need a database connection.

The connection-level behaviour of end_read_transaction() is covered in
tests/integration/test_db_session.py.
"""

import pytest
from sqlalchemy import CheckConstraint, Column, ForeignKey, Index, Integer, MetaData, Table, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column
from sqlalchemy.schema import CreateIndex, CreateTable

from screening_room.db import NAMING_CONVENTION, Base, PendingChangesError, end_read_transaction


def test_base_uses_the_naming_convention() -> None:
    assert Base.metadata.naming_convention == NAMING_CONVENTION


def test_naming_convention_produces_predictable_names() -> None:
    # A throwaway MetaData, so this test doesn't add tables to the app's Base.
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    Table("teams", metadata, Column("id", Integer, primary_key=True))
    members = Table(
        "members",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("email", Text, unique=True),
        Column("team_id", ForeignKey("teams.id")),
        Column("rating", Integer),
        CheckConstraint("rating BETWEEN 1 AND 5", name="rating_range"),
    )
    index = Index(None, members.c.team_id)

    # Names come from the naming convention, so SQLAlchemy's default dialect is enough.
    ddl = str(CreateTable(members).compile())
    index_ddl = str(CreateIndex(index).compile())

    assert "CONSTRAINT pk_members PRIMARY KEY" in ddl
    assert "CONSTRAINT uq_members_email UNIQUE" in ddl
    assert "CONSTRAINT fk_members_team_id_teams FOREIGN KEY" in ddl
    assert "CONSTRAINT ck_members_rating_range CHECK" in ddl
    assert index_ddl.startswith("CREATE INDEX ix_members_team_id")


class _TestBase(DeclarativeBase):
    """Separate from the app's Base so test models never reach migrations."""


class _Note(_TestBase):
    __tablename__ = "notes"
    id: Mapped[int] = mapped_column(primary_key=True)


def test_end_read_transaction_refuses_to_discard_pending_changes() -> None:
    # An unbound Session: add() only records the object, nothing touches a database.
    session = Session()
    session.add(_Note(id=1))

    with pytest.raises(PendingChangesError):
        end_read_transaction(session)

    assert session.new, "the pending change must still be there"


def test_end_read_transaction_without_changes_succeeds() -> None:
    session = Session()

    end_read_transaction(session)

    assert not session.in_transaction()
