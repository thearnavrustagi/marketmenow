from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from adapters.instagram.reels.template_loader import ReelTemplateLoader


def _minimal_template(
    template_id: str = "test",
    *,
    beats: list[dict] | None = None,
    pipeline: dict | None = None,
) -> dict:
    if beats is None:
        beats = [
            {
                "id": "intro",
                "scene": "IntroScene",
                "audio": {"type": "tts", "text": "Hello"},
            },
        ]
    tmpl: dict = {
        "id": template_id,
        "name": "Test Template",
        "beats": beats,
    }
    if pipeline is not None:
        tmpl["pipeline"] = pipeline
    return tmpl


def _write_template(tmp_path: Path, template_id: str, data: dict) -> None:
    path = tmp_path / f"{template_id}.yaml"
    path.write_text(yaml.dump(data))


class TestListTemplates:
    def test_discovers_yaml_files(self, tmp_path: Path) -> None:
        _write_template(tmp_path, "alpha", _minimal_template("alpha"))
        _write_template(tmp_path, "beta", _minimal_template("beta"))
        (tmp_path / "not_yaml.txt").write_text("ignore")

        loader = ReelTemplateLoader(tmp_path)
        templates = loader.list_templates()
        assert "alpha" in templates
        assert "beta" in templates
        assert "not_yaml" not in templates

    def test_empty_dir(self, tmp_path: Path) -> None:
        loader = ReelTemplateLoader(tmp_path)
        assert loader.list_templates() == []


class TestLoad:
    def test_basic(self, tmp_path: Path) -> None:
        _write_template(tmp_path, "demo", _minimal_template("demo"))
        loader = ReelTemplateLoader(tmp_path)
        tmpl = loader.load("demo")
        assert tmpl.id == "demo"
        assert tmpl.name == "Test Template"
        assert len(tmpl.beats) == 1
        assert tmpl.beats[0].id == "intro"

    def test_missing_raises(self, tmp_path: Path) -> None:
        loader = ReelTemplateLoader(tmp_path)
        with pytest.raises(FileNotFoundError, match="ghost"):
            loader.load("ghost")

    def test_with_pipeline(self, tmp_path: Path) -> None:
        data = _minimal_template(
            "pipe",
            pipeline={
                "steps": [
                    {"id": "s1", "type": "rubric", "inputs": {"img": "test.png"}},
                ],
            },
        )
        _write_template(tmp_path, "pipe", data)
        loader = ReelTemplateLoader(tmp_path)
        tmpl = loader.load("pipe")
        assert len(tmpl.pipeline.steps) == 1
        assert tmpl.pipeline.steps[0].type == "rubric"

    def test_defaults(self, tmp_path: Path) -> None:
        _write_template(tmp_path, "def", _minimal_template("def"))
        loader = ReelTemplateLoader(tmp_path)
        tmpl = loader.load("def")
        assert tmpl.aspect_ratio == "9:16"
        assert tmpl.fps == 30
        assert tmpl.composition_id == "ReelFromTemplate"

    def test_transitions_parsed(self, tmp_path: Path) -> None:
        data = _minimal_template(
            "trans",
            beats=[
                {
                    "id": "b1",
                    "scene": "S1",
                    "audio": {"type": "tts", "text": "Hi"},
                    "entry_transition": {"type": "fade", "duration_frames": 10},
                    "exit_transition": {"type": "slide", "direction": "left"},
                },
            ],
        )
        _write_template(tmp_path, "trans", data)
        loader = ReelTemplateLoader(tmp_path)
        tmpl = loader.load("trans")
        assert tmpl.beats[0].entry_transition.type == "fade"
        assert tmpl.beats[0].entry_transition.duration_frames == 10
        assert tmpl.beats[0].exit_transition.type == "slide"


class TestValidate:
    def test_valid_template(self, tmp_path: Path) -> None:
        _write_template(tmp_path, "ok", _minimal_template("ok"))
        loader = ReelTemplateLoader(tmp_path)
        issues = loader.validate("ok")
        assert issues == []

    def test_no_beats(self, tmp_path: Path) -> None:
        _write_template(tmp_path, "empty", _minimal_template("empty", beats=[]))
        loader = ReelTemplateLoader(tmp_path)
        issues = loader.validate("empty")
        assert any("no beats" in i for i in issues)

    def test_duplicate_beat_ids(self, tmp_path: Path) -> None:
        beats = [
            {"id": "dup", "scene": "S1", "audio": {"type": "tts", "text": "a"}},
            {"id": "dup", "scene": "S2", "audio": {"type": "tts", "text": "b"}},
        ]
        _write_template(tmp_path, "dups", _minimal_template("dups", beats=beats))
        loader = ReelTemplateLoader(tmp_path)
        issues = loader.validate("dups")
        assert any("Duplicate beat ID" in i for i in issues)

    def test_tts_without_text(self, tmp_path: Path) -> None:
        beats = [{"id": "b1", "scene": "S1", "audio": {"type": "tts"}}]
        _write_template(tmp_path, "notext", _minimal_template("notext", beats=beats))
        loader = ReelTemplateLoader(tmp_path)
        issues = loader.validate("notext")
        assert any("TTS audio has no text" in i for i in issues)

    def test_sfx_without_file(self, tmp_path: Path) -> None:
        beats = [{"id": "b1", "scene": "S1", "audio": {"type": "sfx"}}]
        _write_template(tmp_path, "nosfx", _minimal_template("nosfx", beats=beats))
        loader = ReelTemplateLoader(tmp_path)
        issues = loader.validate("nosfx")
        assert any("SFX audio has no file" in i for i in issues)

    def test_invalid_transition_type(self, tmp_path: Path) -> None:
        beats = [
            {
                "id": "b1",
                "scene": "S1",
                "audio": {"type": "tts", "text": "hi"},
                "entry_transition": {"type": "explode"},
            },
        ]
        _write_template(tmp_path, "badtr", _minimal_template("badtr", beats=beats))
        loader = ReelTemplateLoader(tmp_path)
        issues = loader.validate("badtr")
        assert any("explode" in i for i in issues)

    def test_pipeline_step_missing_id(self, tmp_path: Path) -> None:
        data = _minimal_template(
            "noid",
            pipeline={"steps": [{"id": "", "type": "llm"}]},
        )
        _write_template(tmp_path, "noid", data)
        loader = ReelTemplateLoader(tmp_path)
        issues = loader.validate("noid")
        assert any("missing 'id'" in i for i in issues)

    def test_pipeline_step_missing_type(self, tmp_path: Path) -> None:
        data = _minimal_template(
            "notype",
            pipeline={"steps": [{"id": "s1", "type": ""}]},
        )
        _write_template(tmp_path, "notype", data)
        loader = ReelTemplateLoader(tmp_path)
        issues = loader.validate("notype")
        assert any("missing 'type'" in i for i in issues)

    def test_missing_template(self, tmp_path: Path) -> None:
        loader = ReelTemplateLoader(tmp_path)
        issues = loader.validate("nonexistent")
        assert any("Failed to load" in i for i in issues)
