from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base

from config import settings

# Initialize engine and session factory as None.
# They will be created by initialize_database() in each worker process.
engine = None
AsyncSessionLocal = None

# Base class for our declarative models
Base = declarative_base()

def initialize_database():
    """
    Initializes the database engine and session factory.
    This function should be called once per process (e.g., in a Celery worker).
    """
    global engine, AsyncSessionLocal

    if engine is None:
        print("Initializing database engine...")
        engine = create_async_engine(
            settings.database_url,
            future=True,
            echo=False,  # Set to True for debugging SQL queries
        )
        AsyncSessionLocal = async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        print("Database engine initialized.")

async def get_db_session() -> AsyncSession:
    """
    Dependency function that yields a new SQLAlchemy async session.
    Ensures that the database is initialized before creating a session.
    """
    if AsyncSessionLocal is None:
        # This is a fallback in case initialization didn't run.
        initialize_database()

    async with AsyncSessionLocal() as session:
        yield session