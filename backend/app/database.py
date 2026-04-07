"""
Orbi — database engine and session factory.
Swap DATABASE_URL to postgresql+asyncpg://... for production.
"""
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DB_ECHO,
    future=True,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

class Base(DeclarativeBase):
    pass

async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        # We removed 'await session.commit()' from here.
        # The session will now only commit if WE tell it to in the code.
        try:
            yield session
            await session.commit() # Still not implemented in provisioning
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
