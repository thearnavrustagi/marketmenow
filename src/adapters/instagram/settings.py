from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_PACKAGE_DIR = Path(__file__).resolve().parent


class InstagramSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Figma
    figma_api_token: str = ""

    # TTS
    tts_provider: str = "elevenlabs"

    # ElevenLabs
    elevenlabs_api_key: str = ""
    elevenlabs_voice_id: str = ""
    elevenlabs_gradeasy_voice_id: str = ""

    # Local TTS (macOS say / espeak-ng) voice overrides
    local_tts_gradeasy_voice: str = "Daniel"
    local_tts_kid_voice: str = "Junior"

    # Kokoro TTS (local neural TTS via kokoro-onnx)
    kokoro_model_dir: str = ""
    kokoro_speed: float = 1.25
    kokoro_lang: str = "en-us"
    kokoro_teacher_voice: str = "af_bella"
    kokoro_gradeasy_voice: str = "am_adam"
    kokoro_child_voice: str = "am_fenrir"
    kokoro_child_pitch_semitones: float = 2.0

    # OpenAI TTS
    openai_api_key: str = ""
    openai_tts_voice: str = "alloy"
    openai_tts_model: str = "tts-1"

    # Vertex AI / Gemini
    google_application_credentials: Path = Path("vertex.json")
    vertex_ai_project: str = ""
    vertex_ai_location: str = "us-central1"

    # Instagram Graph API
    instagram_access_token: str = ""
    instagram_business_account_id: str = ""

    # Paths
    output_dir: Path = Path("output")
    remotion_project_dir: Path = _PACKAGE_DIR / "reels" / "remotion"
