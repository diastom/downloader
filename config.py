from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List

class Settings(BaseSettings):
    """
    Loads and validates application settings from environment variables.
    """
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8')

    bot_token: str

    public_archive_channel_id: int
    private_archive_channel_id: int

    # --- Optional: For Local Bot API Server ---
    # Set to True if you are running your own Bot API server.
    local_bot_api_enabled: bool = False
    # The absolute base path where your local Bot API server stores files.
    local_bot_api_server_data_dir: str | None = None

    redis_url: str = "redis://localhost:6379/0"
    admin_ids_str: str
    database_url: str = "postgresql+asyncpg://user:password@localhost:5432/dlbot_db"

    @property
    def admin_ids(self) -> List[int]:
        return [int(admin_id.strip()) for admin_id in self.admin_ids_str.split(',') if admin_id.strip()]

settings = Settings()