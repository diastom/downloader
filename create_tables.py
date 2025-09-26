import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from config import settings
from utils.db_session import Base

# All your models need to be imported here for SQLAlchemy to see them
from utils.models import (
    User,
    Thumbnail,
    WatermarkSetting,
    UrlCache,
    PublicArchive,
    BotText,
    DownloadRecord,
    TaskUsage,
)

async def create_db_tables():
    """
    Connects to the database and creates tables defined in the models.
    """
    print("Connecting to the database...")
    engine = create_async_engine(settings.database_url, echo=True)

    async with engine.begin() as conn:
        print("Creating all tables based on models (if they don't exist)...")
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text(
            "ALTER TABLE IF EXISTS public.users "
            "ADD COLUMN IF NOT EXISTS sub_encode_limit INTEGER DEFAULT -1"
        ))
        await conn.execute(text(
            "ALTER TABLE public.users "
            "ALTER COLUMN sub_encode_limit SET DEFAULT -1"
        ))
        await conn.execute(text(
            "UPDATE public.users SET sub_encode_limit = -1 "
            "WHERE sub_encode_limit IS NULL"
        ))

    print("Tables created successfully.")
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(create_db_tables())