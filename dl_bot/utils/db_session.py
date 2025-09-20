from sqlalchemy.ext.asyncio import create_async_engine, sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base

from ..config import settings

# Create an asynchronous engine to connect to the PostgreSQL database
engine = create_async_engine(
    settings.database_url,
    future=True,
    echo=False, # Set to True to see SQL queries in the logs
)

# Create a session factory for creating new async sessions
AsyncSessionLocal = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# Base class for our declarative models
Base = declarative_base()

async def get_db_session() -> AsyncSession:
    """
    Dependency function that yields a new SQLAlchemy async session.
    """
    async with AsyncSessionLocal() as session:
        yield session
