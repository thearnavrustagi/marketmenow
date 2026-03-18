from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from elevenlabs import AsyncElevenLabs

from ..tts import SynthesisResult, WordTiming, _mp3_duration_estimate


class ElevenLabsTTS:
    """ElevenLabs TTS backend with character-level timestamp support."""

    def __init__(
        self,
        api_key: str,
        voice_id: str,
        output_dir: Path,
        model_id: str = "eleven_multilingual_v2",
    ) -> None:
        self._client = AsyncElevenLabs(api_key=api_key)
        self._voice_id = voice_id
        self._output_dir = output_dir / "tts"
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._model_id = model_id

    async def synthesize(self, text: str, voice_id: str = "") -> SynthesisResult:
        effective_voice = voice_id or self._voice_id
        if not effective_voice:
            raise RuntimeError(
                "No ElevenLabs voice ID configured. "
                "Set ELEVENLABS_VOICE_ID in your .env file."
            )
        response = await self._client.text_to_speech.convert_with_timestamps(
            voice_id=effective_voice,
            text=text,
            model_id=self._model_id,
            output_format="mp3_44100_128",
        )

        audio_bytes = b""
        word_timings: list[WordTiming] = []

        if hasattr(response, "audio_base64") and response.audio_base64:
            import base64

            audio_bytes = base64.b64decode(response.audio_base64)
        elif hasattr(response, "audio") and response.audio:
            if isinstance(response.audio, bytes):
                audio_bytes = response.audio
            else:
                import base64

                audio_bytes = base64.b64decode(response.audio)

        if hasattr(response, "alignment") and response.alignment:
            alignment = response.alignment
            chars = getattr(alignment, "characters", []) or []
            starts = getattr(alignment, "character_start_times_seconds", []) or []
            ends = getattr(alignment, "character_end_times_seconds", []) or []
            word_timings = _chars_to_words(chars, starts, ends)

        filename = f"{uuid4().hex}.mp3"
        audio_path = self._output_dir / filename
        audio_path.write_bytes(audio_bytes)

        duration = _mp3_duration_estimate(audio_bytes)
        if word_timings:
            duration = max(duration, word_timings[-1].end_seconds)

        return SynthesisResult(
            audio_path=audio_path,
            duration_seconds=duration,
            word_timings=word_timings,
        )

    async def get_audio_duration(self, audio_path: Path) -> float:
        data = audio_path.read_bytes()
        return _mp3_duration_estimate(data)


def _chars_to_words(
    chars: list[str],
    starts: list[float],
    ends: list[float],
) -> list[WordTiming]:
    """Aggregate character-level timestamps into word-level timings."""
    if not chars:
        return []

    words: list[WordTiming] = []
    current_word = ""
    word_start = 0.0
    word_end = 0.0

    for ch, s, e in zip(chars, starts, ends):
        if ch == " " and current_word:
            words.append(
                WordTiming(text=current_word, start_seconds=word_start, end_seconds=word_end)
            )
            current_word = ""
        elif ch != " ":
            if not current_word:
                word_start = s
            current_word += ch
            word_end = e

    if current_word:
        words.append(WordTiming(text=current_word, start_seconds=word_start, end_seconds=word_end))

    return words
