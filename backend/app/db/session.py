from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.db.url import resolve_async_database_url

try:
    from app.core.config import settings
    _debug = getattr(settings, "DEBUG", False)
    _settings_db_url = getattr(settings, "DATABASE_URL", "")
    _pool_size = getattr(settings, "DB_POOL_SIZE", 5)
    _max_overflow = getattr(settings, "DB_MAX_OVERFLOW", 5)
    _pool_timeout = getattr(settings, "DB_POOL_TIMEOUT_SECONDS", 10.0)
    _pool_recycle = getattr(settings, "DB_POOL_RECYCLE_SECONDS", 1800)
    _command_timeout = getattr(settings, "DB_COMMAND_TIMEOUT_SECONDS", 30.0)
    _statement_timeout = getattr(settings, "DB_STATEMENT_TIMEOUT_MS", 30_000)
except Exception:
    _debug = False
    _settings_db_url = ""
    _pool_size = 5
    _max_overflow = 5
    _pool_timeout = 10.0
    _pool_recycle = 1800
    _command_timeout = 30.0
    _statement_timeout = 30_000

_db_url = resolve_async_database_url(_settings_db_url)

engine = create_async_engine(
    _db_url,
    echo=_debug,
    pool_pre_ping=True,
    pool_size=_pool_size,
    max_overflow=_max_overflow,
    pool_timeout=_pool_timeout,
    pool_recycle=_pool_recycle,
    pool_use_lifo=True,
    connect_args={
        "command_timeout": _command_timeout,
        "server_settings": {
            "application_name": "ilya-api",
            "statement_timeout": str(_statement_timeout),
        },
    },
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
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
