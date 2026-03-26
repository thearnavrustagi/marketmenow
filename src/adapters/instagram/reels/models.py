from __future__ import annotations

import enum

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


class TransitionSpec(BaseModel, frozen=True):
    """Entry or exit transition applied to a beat in the Remotion renderer."""

    type: str = "none"
    duration_frames: int = 0
    direction: str = ""
    easing: str = ""


class BeatDefinition(BaseModel, frozen=True):
    """A single beat in a reel template, as defined in YAML."""

    id: str
    scene: str
    audio: AudioSpec
    duration: str = "from_audio"
    fixed_seconds: float = 0.0
    pad_seconds: float = 0.0
    visual: dict[str, object] = Field(default_factory=dict)
    entry_transition: TransitionSpec = Field(default_factory=TransitionSpec)
    exit_transition: TransitionSpec = Field(default_factory=TransitionSpec)


class QuestionTypeDef(BaseModel, frozen=True):
    """A worksheet question type available for random selection."""

    type: str
    description: str = ""
    needs_image_prompt: bool = False


class WorksheetConfig(BaseModel, frozen=True):
    """Configuration for automatic worksheet generation."""

    question_types: list[QuestionTypeDef] = Field(default_factory=list)
    subjects: list[str] = Field(default_factory=list)
    num_questions_min: int = 1
    num_questions_max: int = 3
    fill_prompt: str = ""


class PipelineStepDef(BaseModel, frozen=True):
    """A single step in the template's content-generation pipeline."""

    id: str
    type: str
    inputs: dict[str, object] = Field(default_factory=dict)
    output_var: str = ""
    output_fields: list[str] = Field(default_factory=list)


class PipelineConfig(BaseModel, frozen=True):
    """Declarative pipeline configuration embedded in a reel template."""

    steps: list[PipelineStepDef] = Field(default_factory=list)


class ReelTemplate(BaseModel, frozen=True):
    """Parsed and validated YAML reel template."""

    id: str
    name: str
    aspect_ratio: str = "9:16"
    fps: int = 30
    composition_id: str = "ReelFromTemplate"
    variables: list[str] = Field(default_factory=list)
    beats: list[BeatDefinition]
    pipeline: PipelineConfig = Field(default_factory=PipelineConfig)
    default_visual: dict[str, object] = Field(default_factory=dict)
    caption_template: str = ""
    hashtags: list[str] = Field(default_factory=list)
    hook_lines: list[str] = Field(default_factory=list)
    worksheet: WorksheetConfig | None = None


class ResolvedBeat(BaseModel, frozen=True):
    """A beat with all template variables resolved and audio duration computed."""

    id: str
    scene: str
    audio_path: str
    duration_seconds: float
    duration_frames: int
    visual: dict[str, object] = Field(default_factory=dict)
    subtitle: str = ""
    entry_transition: TransitionSpec = Field(default_factory=TransitionSpec)
    exit_transition: TransitionSpec = Field(default_factory=TransitionSpec)


class ReelScript(BaseModel, frozen=True):
    """Fully resolved reel ready for Remotion rendering."""

    template_id: str
    fps: int
    aspect_ratio: str
    composition_id: str = "ReelFromTemplate"
    total_duration_frames: int
    beats: list[ResolvedBeat]
    variables: dict[str, object] = Field(default_factory=dict)
