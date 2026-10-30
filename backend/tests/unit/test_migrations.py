"""Migration history checks that don't need a database.

CI also runs the migrations against a fresh PostgreSQL (see ci.yml).
"""

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"


def test_migration_history_has_a_single_head() -> None:
    # Two heads means two migrations claim the same parent (e.g. after merging
    # two branches). `alembic upgrade head` would then refuse to run.
    scripts = ScriptDirectory.from_config(Config(str(ALEMBIC_INI)))

    assert len(scripts.get_heads()) == 1, f"multiple heads: {scripts.get_heads()}"
