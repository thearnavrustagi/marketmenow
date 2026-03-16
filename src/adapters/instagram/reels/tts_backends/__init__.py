from __future__ import annotations

from pathlib import Path

from ..tts import TTSProvider, TTSService


def create_tts_service(
    provider: TTSProvider,
    output_dir: Path,
    *,
    elevenlabs_api_key: str = "",
    elevenlabs_voice_id: str = "",
    elevenlabs_model_id: str = "eleven_multilingual_v2",
    openai_api_key: str = "",
    openai_voice: str = "alloy",
    openai_model: str = "tts-1",
    kokoro_model_dir: Path | None = None,
    kokoro_default_voice: str = "af_bella",
    kokoro_speed: float = 1.0,
    kokoro_lang: str = "en-us",
    kokoro_voice_overrides: dict[str, str] | None = None,
    kokoro_pitch_shift_semitones: dict[str, float] | None = None,
) -> TTSService:
    """Factory that returns the correct TTS backend based on provider enum."""
    if provider == TTSProvider.ELEVENLABS:
        from .elevenlabs import ElevenLabsTTS

        return ElevenLabsTTS(
            api_key=elevenlabs_api_key,
            voice_id=elevenlabs_voice_id,
            output_dir=output_dir,
            model_id=elevenlabs_model_id,
        )

    if provider == TTSProvider.OPENAI:
        from .openai import OpenAITTS

        return OpenAITTS(
            api_key=openai_api_key,
            voice=openai_voice,
            model=openai_model,
            output_dir=output_dir,
        )

    if provider == TTSProvider.LOCAL:
        from .local import LocalTTS

        return LocalTTS(output_dir=output_dir)

    if provider == TTSProvider.KOKORO:
        from .kokoro import KokoroTTS

        return KokoroTTS(
            output_dir=output_dir,
            model_dir=kokoro_model_dir,
            default_voice=kokoro_default_voice,
            speed=kokoro_speed,
            lang=kokoro_lang,
            voice_overrides=kokoro_voice_overrides,
            pitch_shift_semitones=kokoro_pitch_shift_semitones,
        )

    raise ValueError(f"Unknown TTS provider: {provider}")
