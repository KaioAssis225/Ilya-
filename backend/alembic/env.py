from logging.config import fileConfig
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config
from alembic import context
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models.base import Base

config = context.config

# Read DATABASE_URL directly from the environment rather than through Pydantic
# settings. During Railway's pre-deploy stage, reference variables such as
# ${{Postgres.DATABASE_URL}} are expanded directly into the process
# environment, but Pydantic's BaseSettings may attempt to load from a .env
# file first and miss the injected value. Reading os.environ directly ensures
# Alembic always sees the value Railway actually provides.
_db_url = os.environ.get("DATABASE_URL", "")
if not _db_url:
    raise RuntimeError(
        "DATABASE_URL environment variable is not set. Ensure it is "
        "configured for this service (e.g. as a Railway reference variable)."
    )

# Railway provides 'postgresql://' but SQLAlchemy async requires 'postgresql+asyncpg://'
if _db_url.startswith("postgresql://"):
    _db_url = _db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
config.set_main_option("sqlalchemy.url", _db_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
