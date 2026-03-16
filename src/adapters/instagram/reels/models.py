from __future__ import annotations

import enum
from pathlib import Path

from pydantic import BaseModel, Field


class AudioType(str, enum.Enum):
    TTS = "tts"
    SFX = "sfx"


class AudioSpec(BaseModel, frozen=True):
    """Describes the audio for a single beat -- either TTS text or a static SFX file."""

    type: AudioType
    text: str = ""
    file: str = ""
    voice: str = ""


class VisualSpec(BaseModel, frozen=True):
    """Arbitrary visual properties passed through to the Remotion scene component."""

    props: dict[str, object] = Field(default_factory=dict)


class BeatDefinition(BaseModel, frozen=True):
    """A single beat in a reel template, as defined in YAML."""

    id: str
    scene: str
    audio: AudioSpec
    duration: str = "from_audio"
    fixed_seconds: float = 0.0
    pad_seconds: float = 0.0
    visual: dict[str, object] = Field(default_factory=dict)


class ReelTemplate(BaseModel, frozen=True):
    """Parsed and validated YAML reel template."""

    id: str
    name: str
    aspect_ratio: str = "9:16"
    fps: int = 30
    variables: list[str] = Field(default_factory=list)
    beats: list[BeatDefinition]


class ResolvedBeat(BaseModel, frozen=True):
    """A beat with all template variables resolved and audio duration computed."""

    id: str
    scene: str
    audio_path: str
    duration_seconds: float
    duration_frames: int
    visual: dict[str, object] = Field(default_factory=dict)
    subtitle: str = ""


class ReelScript(BaseModel, frozen=True):
    """Fully resolved reel ready for Remotion rendering."""

    template_id: str
    fps: int
    aspect_ratio: str
    total_duration_frames: int
    beats: list[ResolvedBeat]
    variables: dict[str, object] = Field(default_factory=dict)
