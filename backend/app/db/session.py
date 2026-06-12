"""Async database session."""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings
from app.db.models import Base

_settings = get_settings()
engine = create_async_engine(_settings.database_url, echo=_settings.app_env == "development")
async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db() -> None:
    """Create tables (M1); replace with Alembic in M2."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
