from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import httpx

from ..tts import SynthesisResult, WordTiming, _mp3_duration_estimate

_OPENAI_TTS_URL = "https://api.openai.com/v1/audio/speech"


class OpenAITTS:
    """OpenAI TTS backend (tts-1 / tts-1-hd).

    Uses the REST API directly via httpx to avoid pulling in the full
    ``openai`` SDK as a hard dependency.  Word-level timestamps are not
    available from this endpoint so ``word_timings`` is always empty.
    """

    def __init__(
        self,
        api_key: str,
        output_dir: Path,
        voice: str = "alloy",
        model: str = "tts-1",
    ) -> None:
        self._api_key = api_key
        self._voice = voice
        self._model = model
        self._output_dir = output_dir / "tts"
        self._output_dir.mkdir(parents=True, exist_ok=True)

    async def synthesize(self, text: str, voice_id: str = "") -> SynthesisResult:
        effective_voice = voice_id or self._voice
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                _OPENAI_TTS_URL,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self._model,
                    "input": text,
                    "voice": effective_voice,
                    "response_format": "mp3",
                },
            )
            resp.raise_for_status()
            audio_bytes = resp.content

        filename = f"{uuid4().hex}.mp3"
        audio_path = self._output_dir / filename
        audio_path.write_bytes(audio_bytes)

        duration = _mp3_duration_estimate(audio_bytes)

        return SynthesisResult(
            audio_path=audio_path,
            duration_seconds=duration,
            word_timings=[],
        )

    async def get_audio_duration(self, audio_path: Path) -> float:
        data = audio_path.read_bytes()
        return _mp3_duration_estimate(data)
