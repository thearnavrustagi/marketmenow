from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class YouTubeSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    youtube_client_id: str = ""
    youtube_client_secret: str = ""
    youtube_refresh_token: str = ""
    youtube_default_privacy: str = "private"
    youtube_default_category_id: str = "27"
