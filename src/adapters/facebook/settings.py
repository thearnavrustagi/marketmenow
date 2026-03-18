from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class FacebookSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Cookie login -- grab c_user and xs from DevTools > Application > Cookies > facebook.com
    facebook_c_user: str = ""
    facebook_xs: str = ""

    # Comma-separated group IDs or URLs for teacher group posting
    facebook_group_ids: str = ""

    # Session / browser paths
    facebook_session_path: Path = Path(".facebook_session.json")
    facebook_user_data_dir: Path = Path(".facebook_browser_profile")

    # Browser
    headless: bool = False
    slow_mo_ms: int = 50
    proxy_url: str = ""
    viewport_width: int = 1280
    viewport_height: int = 900
