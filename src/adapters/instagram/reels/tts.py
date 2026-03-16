from __future__ import annotations

import enum
from pathlib import Path
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field


class WordTiming(BaseModel, frozen=True):
    """Timing information for a word or character group in TTS output."""

    text: str
    start_seconds: float
    end_seconds: float


class SynthesisResult(BaseModel, frozen=True):
    """Result of a TTS synthesis call."""

    audio_path: Path
    duration_seconds: float
    word_timings: list[WordTiming] = Field(default_factory=list)


class TTSProvider(str, enum.Enum):
    ELEVENLABS = "elevenlabs"
    OPENAI = "openai"
    LOCAL = "local"
    KOKORO = "kokoro"


@runtime_checkable
class TTSService(Protocol):
    """Protocol that all TTS backends must satisfy."""

    async def synthesize(self, text: str, voice_id: str = "") -> SynthesisResult: ...

    async def get_audio_duration(self, audio_path: Path) -> float: ...


def _mp3_duration_estimate(data: bytes) -> float:
    """Rough MP3 duration estimate from file size assuming ~128kbps CBR."""
    return len(data) * 8 / 128_000
