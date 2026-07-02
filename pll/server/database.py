"""
Database setup — SQLite + SQLAlchemy async.
Uses aiosqlite for async SQLite access.
"""
import os
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from config import DATABASE_URL

engine = create_async_engine(DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def init_db():
    """Create all tables if they don't exist, run migrations."""
    from models import Project, Artifact, AgentSession, GCAVault, Package, Conversation  # noqa: F401
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    # Auto-migration: add source_content to packages if missing
    try:
        async with engine.begin() as conn:
            from sqlalchemy import text
            await conn.execute(text("ALTER TABLE packages ADD COLUMN source_content TEXT DEFAULT ''"))
    except Exception:
        pass  # column already exists


async def get_db() -> AsyncSession:
    """FastAPI dependency: yields an async DB session."""
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()
