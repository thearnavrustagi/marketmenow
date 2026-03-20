from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class TwitterSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    twitter_username: str = ""
    twitter_password: str = ""
    twitter_auth_token: str = ""
    twitter_ct0: str = ""
    twitter_session_path: Path = Path(".twitter_session.json")
    twitter_user_data_dir: Path = Path(".twitter_browser_profile")

    # Vertex AI / Gemini
    google_application_credentials: Path = Path("vertex.json")
    vertex_ai_project: str = ""
    vertex_ai_location: str = "us-central1"
    gemini_model: str = "gemini-3.1-flash-preview"

    # Rate limiting
    max_replies_per_day: int = 20
    min_delay_seconds: int = 300
    max_delay_seconds: int = 600
    cooldown_hours: int = 24

    # Browser
    headless: bool = False
    slow_mo_ms: int = 50
    proxy_url: str = ""
    viewport_width: int = 1280
    viewport_height: int = 900

    # Targets
    targets_path: Path = Path(__file__).resolve().parent / "targets.yaml"

    # Audit
    audit_log_path: Path = Path(".twitter_audit_log.jsonl")
    reply_history_path: Path = Path(".twitter_reply_history.json")

    # In-context learning from top-performing posts
    top_examples_path: Path = Path(".twitter_top_examples.json")
    max_examples_in_prompt: int = 5
    examples_max_age_hours: int = 168  # re-collect weekly
