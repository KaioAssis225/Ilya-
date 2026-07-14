from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.db.url import resolve_async_database_url

try:
    from app.core.config import settings
    _debug = getattr(settings, "DEBUG", False)
    _settings_db_url = getattr(settings, "DATABASE_URL", "")
except Exception:
    _debug = False
    _settings_db_url = ""

_db_url = resolve_async_database_url(_settings_db_url)

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
