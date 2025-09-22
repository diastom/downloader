from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from dl_bot.config import settings
from dl_bot.utils.db_session import AsyncSessionLocal
from dl_bot.bot.handlers import admin, common, downloader, settings as user_settings, video
from dl_bot.bot.middlewares import DbSessionMiddleware


def setup_dispatcher() -> Dispatcher:
    """
    Creates and configures the main Dispatcher instance, registering all routers.
    """
    # Using simple in-memory storage for FSM. For production, RedisStorage is better.
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    # Register our custom middleware to provide a session to each handler
    dp.update.middleware(DbSessionMiddleware(session_pool=AsyncSessionLocal))

    # Include all the routers from the handlers package
    dp.include_router(common.router)
    dp.include_router(admin.router)
    dp.include_router(user_settings.router)
    dp.include_router(video.router)
    dp.include_router(downloader.router) # This should be last as it has a broad regex

    return dp

# Create a single bot instance to be used across the application
bot = Bot(token=settings.bot_token, parse_mode="HTML")
