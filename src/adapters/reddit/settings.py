from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class RedditSettings(BaseSettings):
    """Reddit adapter configuration — loaded from env vars / ``.env`` file."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Auth (cookie-based) ------------------------------------------------
    reddit_session: str = ""
    reddit_username: str = ""
    reddit_user_agent: str = "marketmenow:v0.1 (by u/GradeasyBot)"

    # Vertex AI / Gemini --------------------------------------------------
    google_application_credentials: Path | None = None
    vertex_ai_project: str = ""
    vertex_ai_location: str = "us-central1"
    gemini_model: str = "gemini-2.5-flash"

    # Rate limits ----------------------------------------------------------
    max_comments_per_day: int = 10
    min_delay_seconds: int = 120
    max_delay_seconds: int = 300
    cooldown_hours: int = 6
    mention_rate: int = 10

    # Paths ----------------------------------------------------------------
    targets_path: Path = Path("src/adapters/reddit/targets.yaml")
    audit_log_path: Path = Path("output/reddit/audit.jsonl")
    comment_history_path: Path = Path("output/reddit/comment_history.json")
