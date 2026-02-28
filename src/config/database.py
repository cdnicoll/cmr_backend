"""Transaction pooler and async database."""
import asyncpg
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import sessionmaker

from src.models.config import load_settings

# Convert postgresql:// to postgresql+asyncpg:// for SQLAlchemy
def _pooler_url() -> str:
    url = load_settings().transaction_pooler_url
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


_engine = None
_session_factory = None


def get_engine():
    """Get or create async engine."""
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            _pooler_url(),
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,
            echo=False,
        )
    return _engine


def get_transaction_session_factory() -> async_sessionmaker[AsyncSession]:
    """Get async session factory."""
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )
    return _session_factory


async def check_transaction_pooler_health() -> bool:
    """Check if transaction pooler is reachable."""
    try:
        url = load_settings().transaction_pooler_url
        conn = await asyncpg.connect(url, statement_cache_size=0)
        await conn.execute("SELECT 1")
        await conn.close()
        return True
    except Exception:
        return False
