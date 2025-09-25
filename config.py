from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List

class Settings(BaseSettings):
    """
    Loads and validates application settings from environment variables.
    """
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8')

    bot_token: str
    api_id: int
    api_hash: str

    # We now only use the session string.
    session_string: str

    public_archive_chat_id: int
    redis_url: str = "redis://localhost:6379/0"
    admin_ids_str: str
    database_url: str = "postgresql+asyncpg://user:password@localhost:5432/dlbot_db"

    @property
    def admin_ids(self) -> List[int]:
        return [int(admin_id.strip()) for admin_id in self.admin_ids_str.split(',') if admin_id.strip()]

settings = Settings()