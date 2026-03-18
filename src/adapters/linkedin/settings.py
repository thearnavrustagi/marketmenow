from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class LinkedInSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── REST API (preferred) ──────────────────────────────────────────
    # OAuth 2.0 app credentials from https://linkedin.com/developers/apps
    linkedin_client_id: str = ""
    linkedin_client_secret: str = ""
    # Access token (auto-filled by `mmn linkedin auth`).
    # When set, the adapter uses the REST API instead of a browser.
    linkedin_access_token: str = ""
    # Person URN (urn:li:person:xxx) — auto-filled by `mmn linkedin auth`.
    linkedin_person_urn: str = ""
    # LinkedIn API version in YYYYMM format.
    linkedin_api_version: str = "202504"

    # ── Cookie / browser fallback ─────────────────────────────────────
    # Grab li_at from DevTools > Application > Cookies > linkedin.com
    linkedin_li_at: str = ""

    # Organization page URL slug or numeric ID (for posting as an org)
    linkedin_organization_id: str = ""

    # Vertex AI / Gemini (for AI content generation)
    google_application_credentials: Path = Path("vertex.json")
    vertex_ai_project: str = ""
    vertex_ai_location: str = "us-central1"

    # Session / browser paths
    linkedin_session_path: Path = Path(".linkedin_session.json")
    linkedin_user_data_dir: Path = Path(".linkedin_browser_profile")

    # Browser
    headless: bool = False
    slow_mo_ms: int = 50
    proxy_url: str = ""
    viewport_width: int = 1280
    viewport_height: int = 900

    @property
    def use_api(self) -> bool:
        """True when we have enough credentials to use the REST API."""
        return bool(self.linkedin_access_token)

    @property
    def author_urn(self) -> str:
        """The URN to use as the post author.

        When ``linkedin_organization_id`` is set the post is authored by
        the organization page (requires the ``w_organization_social``
        scope or Community Management API access on the LinkedIn app).
        Otherwise falls back to the person URN for personal posting.
        """
        if self.linkedin_organization_id:
            return f"urn:li:organization:{self.linkedin_organization_id}"
        return self.linkedin_person_urn
