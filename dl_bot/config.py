from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List, Optional

class Settings(BaseSettings):
    """
    Loads and validates application settings from environment variables.
    """
    # Load from a .env file in the same directory
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8')

    # Telegram Bot Token from BotFather
    bot_token: str

    # Telegram API credentials from my.telegram.org
    api_id: int
    api_hash: str

    # Telethon Session String
    session_string: str

    # ID of the public channel where videos are archived
    public_archive_chat_id: int

    # URL for the Celery broker and backend
    redis_url: str = "redis://localhost:6379/0"

    # Comma-separated list of admin user IDs
    admin_ids_str: str

    @property
    def admin_ids(self) -> List[int]:
        """
        Parses the comma-separated string of admin IDs into a list of integers.
        """
        return [int(admin_id.strip()) for admin_id in self.admin_ids_str.split(',') if admin_id.strip()]

# Create a single, importable instance of the settings
settings = Settings()
