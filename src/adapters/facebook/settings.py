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

    # Comma-separated page IDs, URLs, or slugs for page posting
    facebook_page_ids: str = ""

    # Session / browser paths
    facebook_session_path: Path = Path(".facebook_session.json")
    facebook_user_data_dir: Path = Path(".facebook_browser_profile")

    # Browser
    headless: bool = False
    slow_mo_ms: int = 50
    proxy_url: str = ""
    viewport_width: int = 1280
    viewport_height: int = 900

    # Vertex AI / Gemini
    google_application_credentials: Path | None = None
    vertex_ai_project: str = ""
    vertex_ai_location: str = "us-central1"
    gemini_model: str = "gemini-2.5-flash"

    # Engagement rate limits (conservative — Facebook bans are hard to recover)
    max_comments_per_day: int = 5
    min_delay_seconds: int = 120
    max_delay_seconds: int = 300
    cooldown_hours: int = 12
    mention_rate: int = 10

    # Engagement paths
    targets_path: Path = Path("src/adapters/facebook/targets.yaml")
    audit_log_path: Path = Path("output/facebook/audit.jsonl")
    comment_history_path: Path = Path("output/facebook/comment_history.json")

    # In-context learning from top-performing comments
    top_examples_path: Path = Path("output/facebook/.facebook_top_examples.json")
    max_examples_in_prompt: int = 5
    examples_max_age_hours: int = 168  # re-collect weekly

    # Epsilon-greedy exploration vs exploitation for ICL.
    epsilon: float = 0.3
