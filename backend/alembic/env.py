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

# Build the database URL from the individual Postgres environment variables
# (PGHOST, PGPORT, PGUSER, PGPASSWORD, PGDATABASE) rather than relying on the
# DATABASE_URL reference variable. Railway does not expand reference
# variables such as ${{Postgres.DATABASE_URL}} until the container is fully
# running, which is after pre-deploy commands (like `alembic upgrade head`)
# execute. The individual PG* variables, however, are generated directly by
# Railway's Postgres template and are available during pre-deploy, so we use
# those to construct the connection string instead.
_pg_host = os.environ.get("PGHOST", "")
_pg_port = os.environ.get("PGPORT", "5432")
_pg_user = os.environ.get("PGUSER", "")
_pg_password = os.environ.get("PGPASSWORD", "")
_pg_database = os.environ.get("PGDATABASE", "")

_missing = [
    name
    for name, value in (
        ("PGHOST", _pg_host),
        ("PGUSER", _pg_user),
        ("PGPASSWORD", _pg_password),
        ("PGDATABASE", _pg_database),
    )
    if not value
]
if _missing:
    raise RuntimeError(
        "Missing required Postgres environment variable(s): "
        f"{', '.join(_missing)}. Ensure they are configured for this service."
    )

_db_url = (
    f"postgresql+asyncpg://{_pg_user}:{_pg_password}@{_pg_host}:{_pg_port}/{_pg_database}"
)
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
