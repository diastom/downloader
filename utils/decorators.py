import time
from functools import wraps
from typing import Dict, Any

from aiogram import types
from aiogram import BaseMiddleware 

from config import settings

# A dictionary to store the last time a user called a command
user_cooldowns: Dict[int, float] = {}
COOLDOWN_SECONDS = 60 # Default cooldown

# TODO: In aiogram 3, this should be an Outer Middleware for better integration.
# For now, a simple decorator will work for handlers.

def cooldown(seconds: int = COOLDOWN_SECONDS):
    """
    A decorator to prevent users from spamming commands.
    This version is adapted for aiogram.
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(message_or_query: types.Message | types.CallbackQuery, *args, **kwargs):
            user_id = message_or_query.from_user.id

            # Admins are not affected by the cooldown
            if user_id in settings.admin_ids:
                return await func(message_or_query, *args, **kwargs)

            last_call_time = user_cooldowns.get(user_id)

            if last_call_time:
                time_passed = time.time() - last_call_time
                if time_passed < seconds:
                    remaining_time = seconds - time_passed

                    # Answer differently based on message or callback query
                    if isinstance(message_or_query, types.Message):
                        await message_or_query.answer(
                            f"لطفاً کمی صبر کنید. شما می‌توانید تا {int(remaining_time)} ثانیه دیگر دوباره تلاش کنید."
                        )
                    elif isinstance(message_or_query, types.CallbackQuery):
                        await message_or_query.answer(
                            text=f"لطفاً کمی صبر کنید. شما می‌توانید تا {int(remaining_time)} ثانیه دیگر دوباره تلاش کنید.",
                            show_alert=True
                        )
                    return

            # Update the cooldown timestamp *before* calling the function
            # to prevent race conditions.
            user_cooldowns[user_id] = time.time()
            return await func(message_or_query, *args, **kwargs)
        return wrapper
    return decorator
