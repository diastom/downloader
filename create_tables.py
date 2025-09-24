import asyncio
from sqlalchemy.ext.asyncio import create_async_engine

from config import settings
from utils.db_session import Base

# All your models need to be imported here for SQLAlchemy to see them
from utils.models import User, Thumbnail, WatermarkSetting, UrlCache, PublicArchive, BotText

async def create_db_tables():
    """
    Connects to the database and creates tables defined in the models.
    """
    print("Connecting to the database...")
    engine = create_async_engine(settings.database_url, echo=True)

    async with engine.begin() as conn:
        print("Creating all tables based on models (if they don't exist)...")
        await conn.run_sync(Base.metadata.create_all)

    print("Tables created successfully.")
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(create_db_tables())