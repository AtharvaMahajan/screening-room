"""baseline

The root of the migration history. It creates nothing: it gives every later
migration a fixed starting point and lets CI exercise upgrade/downgrade before
the first real tables exist.
"""

from collections.abc import Sequence

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
