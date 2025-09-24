from aiogram import Bot
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.client.default import DefaultBotProperties
from config import settings 

# آدرس سرور محلی را مشخص کنید
LOCAL_API_SERVER = TelegramAPIServer.from_base('http://91.107.146.233:8081')

# یک session با timeout بسیار بالا (مثلاً ۳۰ دقیقه) بسازید
session = AiohttpSession(
    api=LOCAL_API_SERVER,
    timeout=1800  # 30 minutes in seconds
)

# یک نمونه bot واحد با این session بسازید
# این نمونه در کل پروژه استفاده خواهد شد
bot = Bot(token=settings.bot_token, session=session, default=DefaultBotProperties(parse_mode='HTML'))