import asyncio
from sqlalchemy.ext.asyncio import create_async_engine

from config import settings
from utils.db_session import Base

# تمام مدل‌های خود را اینجا وارد کنید تا SQLAlchemy آنها را شناسایی کند
from utils.models import User, Thumbnail, WatermarkSetting, VideoCache, BotText

async def create_db_tables():
    """
    متصل به دیتابیس شده و جداول تعریف شده در مدل‌ها را ایجاد می‌کند.
    """
    print("Connecting to the database...")
    # از نام متغیر صحیح که در config.py شما وجود دارد استفاده می‌کنیم
    engine = create_async_engine(settings.database_url, echo=True) # <<-- تغییر در این خط بود

    async with engine.begin() as conn:
        print("Creating all tables based on models...")
        await conn.run_sync(Base.metadata.create_all)

    print("Tables created successfully.")
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(create_db_tables())