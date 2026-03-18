from __future__ import annotations

from adapters.instagram.reels.models import (
    AudioSpec,
    AudioType,
    BeatDefinition,
    PipelineConfig,
    PipelineStepDef,
    ReelScript,
    ReelTemplate,
    ResolvedBeat,
    TransitionSpec,
    VisualSpec,
)


class TestAudioType:
    def test_values(self) -> None:
        assert AudioType.TTS.value == "tts"
        assert AudioType.SFX.value == "sfx"

    def test_from_string(self) -> None:
        assert AudioType("tts") == AudioType.TTS
        assert AudioType("sfx") == AudioType.SFX


class TestAudioSpec:
    def test_defaults(self) -> None:
        spec = AudioSpec(type=AudioType.TTS)
        assert spec.text == ""
        assert spec.file == ""
        assert spec.voice == ""

    def test_tts_with_text(self) -> None:
        spec = AudioSpec(type=AudioType.TTS, text="Hello world", voice="alloy")
        assert spec.text == "Hello world"
        assert spec.voice == "alloy"


class TestTransitionSpec:
    def test_defaults(self) -> None:
        t = TransitionSpec()
        assert t.type == "none"
        assert t.duration_frames == 0
        assert t.direction == ""
        assert t.easing == ""

    def test_custom(self) -> None:
        t = TransitionSpec(type="fade", duration_frames=15, easing="ease-in")
        assert t.type == "fade"


class TestBeatDefinition:
    def test_defaults(self) -> None:
        beat = BeatDefinition(
            id="intro",
            scene="IntroScene",
            audio=AudioSpec(type=AudioType.TTS, text="Hi"),
        )
        assert beat.duration == "from_audio"
        assert beat.fixed_seconds == 0.0
        assert beat.pad_seconds == 0.0
        assert beat.visual == {}
        assert beat.entry_transition.type == "none"
        assert beat.exit_transition.type == "none"


class TestPipelineStepDef:
    def test_defaults(self) -> None:
        step = PipelineStepDef(id="s1", type="llm")
        assert step.inputs == {}
        assert step.output_var == ""
        assert step.output_fields == []


class TestPipelineConfig:
    def test_default_empty(self) -> None:
        cfg = PipelineConfig()
        assert cfg.steps == []


class TestReelTemplate:
    def test_construction(self) -> None:
        tmpl = ReelTemplate(
            id="test",
            name="Test Template",
            beats=[
                BeatDefinition(
                    id="b1",
                    scene="Scene1",
                    audio=AudioSpec(type=AudioType.TTS, text="Hello"),
                ),
            ],
        )
        assert tmpl.id == "test"
        assert tmpl.aspect_ratio == "9:16"
        assert tmpl.fps == 30
        assert tmpl.composition_id == "ReelFromTemplate"
        assert tmpl.variables == []
        assert tmpl.caption_template == ""
        assert tmpl.hashtags == []


class TestResolvedBeat:
    def test_construction(self) -> None:
        beat = ResolvedBeat(
            id="b1",
            scene="Scene1",
            audio_path="/audio/b1.mp3",
            duration_seconds=3.5,
            duration_frames=105,
        )
        assert beat.subtitle == ""
        assert beat.visual == {}


class TestReelScript:
    def test_construction(self) -> None:
        script = ReelScript(
            template_id="test",
            fps=30,
            aspect_ratio="9:16",
            total_duration_frames=300,
            beats=[],
        )
        assert script.composition_id == "ReelFromTemplate"
        assert script.variables == {}


class TestVisualSpec:
    def test_default(self) -> None:
        v = VisualSpec()
        assert v.props == {}
