import os

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

try:
    from app.core.config import settings
    _debug = getattr(settings, "DEBUG", False)
except Exception:
    _debug = False

# Build the database URL from the individual Postgres environment variables
# (PGHOST, PGPORT, PGUSER, PGPASSWORD, PGDATABASE) rather than relying on the
# DATABASE_URL reference variable. Railway does not expand reference
# variables such as ${{Postgres.DATABASE_URL}} until the container is fully
# running, which is after module initialization happens. The individual PG*
# variables, however, are generated directly by Railway's Postgres template
# and are available during application startup, so we use those to
# construct the connection string instead.
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

engine = create_async_engine(
    _db_url,
    echo=_debug,
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
