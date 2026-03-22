from __future__ import annotations

import os
from pathlib import Path

from google import genai


def resolve_gemini_api_key(explicit_api_key: str | None = None) -> str:
    """Resolve Gemini API key from explicit value or environment.

    Supported env vars:
    - GEMINI_API_KEY (preferred)
    - GOOGLE_API_KEY (legacy alias used by some SDKs)
    """
    candidates = (
        explicit_api_key,
        os.getenv("GEMINI_API_KEY"),
        os.getenv("GOOGLE_API_KEY"),
    )
    for value in candidates:
        if value and value.strip():
            return value.strip()
    return ""


def has_genai_credentials(vertex_project: str = "", api_key: str | None = None) -> bool:
    """Return True when either AI Studio API key or Vertex project is configured."""
    return bool(resolve_gemini_api_key(api_key) or vertex_project.strip())


def configure_google_application_credentials(credentials_path: Path | None) -> None:
    """Export GOOGLE_APPLICATION_CREDENTIALS when a service-account file exists."""
    if credentials_path and credentials_path.exists():
        os.environ.setdefault("GOOGLE_APPLICATION_CREDENTIALS", str(credentials_path.resolve()))


def create_genai_client(
    *,
    vertex_project: str = "",
    vertex_location: str = "us-central1",
    api_key: str | None = None,
) -> genai.Client:
    """Create a GenAI client using AI Studio first, then Vertex as fallback.

    Priority:
    1) AI Studio API key via GEMINI_API_KEY / GOOGLE_API_KEY (or explicit api_key)
    2) Vertex AI via vertex_project + vertex_location
    """
    resolved_key = resolve_gemini_api_key(api_key)
    if resolved_key:
        return genai.Client(api_key=resolved_key)

    if not vertex_project.strip():
        raise ValueError(
            "Missing Gemini credentials. Set GEMINI_API_KEY (AI Studio) "
            "or VERTEX_AI_PROJECT (Vertex AI)."
        )

    return genai.Client(
        vertexai=True,
        project=vertex_project,
        location=vertex_location,
    )
