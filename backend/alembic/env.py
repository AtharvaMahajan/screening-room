"""Alembic environment: how migrations connect to the database.

Alembic runs this file for every command (upgrade, downgrade, revision, check).
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

# Import every module's models here so autogenerate can see their tables.
import screening_room.modules.catalog.models  # noqa: F401
import screening_room.modules.identity.models  # noqa: F401
import screening_room.modules.profile.models  # noqa: F401
from screening_room.config import DatabaseSettings
from screening_room.db import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# What autogenerate compares the database against.
target_metadata = Base.metadata

# Only the database URL: migrations must not need the web app's secrets.
DATABASE_URL = DatabaseSettings().database_url


def run_migrations_offline() -> None:
    """`alembic upgrade head --sql`: print the SQL instead of running it."""
    context.configure(
        url=DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against the live database."""
    # NullPool: a one-off command has no use for a connection pool.
    engine = create_engine(DATABASE_URL, poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        # PostgreSQL has transactional DDL, so each run is all-or-nothing.
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
