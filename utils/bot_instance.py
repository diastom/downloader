from aiogram import Bot
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.client.default import DefaultBotProperties
from config import settings

def create_bot_instance():
    """
    Creates and returns a new Bot instance with its own session.
    This factory should be called within each async task to ensure session isolation.
    """
    # آدرس سرور محلی را مشخص کنید
    local_api_server = TelegramAPIServer.from_base(
        'http://91.107.146.233:8081', is_local=True
    )

    # یک session جدید با timeout بسیار بالا (مثلاً ۳۰ دقیقه) بسازید
    session = AiohttpSession(
        api=local_api_server,
        timeout=1800  # 30 minutes in seconds
    )

    # یک نمونه bot جدید با این session بسازید
    return Bot(token=settings.bot_token, session=session, default=DefaultBotProperties(parse_mode='HTML'))

# The global bot instance is removed to prevent sharing across tasks.
# bot = Bot(token=settings.bot_token, session=session, default=DefaultBotProperties(parse_mode='HTML'))