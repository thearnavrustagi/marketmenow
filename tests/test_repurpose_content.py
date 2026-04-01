from __future__ import annotations

import json
from pathlib import Path

import pytest

from marketmenow.core.capsule import CapsuleManager
from marketmenow.core.workflow import WorkflowError
from marketmenow.steps.repurpose_content import (
    extract_text_from_capsule,
    parse_repurpose_result,
    resolve_target_modality,
    validate_repurpose,
)

# ── extract_text_from_capsule ────────────────────────────────────────


def test_extract_text_video_capsule(tmp_path: Path) -> None:
    root = tmp_path / "projects"
    mgr = CapsuleManager(projects_root=root)
    capsule = mgr.create(
        "proj",
        "video",
        caption="Watch this reel!",
        title="AI Grading Demo",
        description="See how AI grades homework",
    )
    capsule_dir = str(mgr._capsule_dir("proj", capsule.capsule_id))
    text = extract_text_from_capsule(capsule_dir, capsule)

    assert "AI Grading Demo" in text
    assert "Watch this reel!" in text
    assert "See how AI grades homework" in text


def test_extract_text_thread_capsule(tmp_path: Path) -> None:
    root = tmp_path / "projects"
    mgr = CapsuleManager(projects_root=root)
    capsule = mgr.create(
        "proj",
        "thread",
        thread_entries=["Tweet one", "Tweet two", "Tweet three"],
    )
    capsule_dir = str(mgr._capsule_dir("proj", capsule.capsule_id))
    text = extract_text_from_capsule(capsule_dir, capsule)

    assert "Tweet one" in text
    assert "Tweet two" in text
    assert "Tweet three" in text


def test_extract_text_with_script_artifacts(tmp_path: Path) -> None:
    root = tmp_path / "projects"
    mgr = CapsuleManager(projects_root=root)
    capsule = mgr.create("proj", "video", caption="test")
    mgr.save_script_artifact(
        "proj",
        capsule.capsule_id,
        "reel_script",
        {"script": "Once upon a time, a teacher used AI to grade papers."},
    )
    capsule_dir = str(mgr._capsule_dir("proj", capsule.capsule_id))
    text = extract_text_from_capsule(capsule_dir, capsule)

    assert "Once upon a time" in text


def test_extract_text_empty_capsule(tmp_path: Path) -> None:
    root = tmp_path / "projects"
    mgr = CapsuleManager(projects_root=root)
    capsule = mgr.create("proj", "video")
    capsule_dir = str(mgr._capsule_dir("proj", capsule.capsule_id))
    text = extract_text_from_capsule(capsule_dir, capsule)

    assert text.strip() == ""


def test_extract_text_no_capsule_dir() -> None:
    """Works with None capsule_dir — just skips script artifacts."""

    class FakeCapsule:
        title = "A Title"
        caption = "A caption"
        description = ""
        thread_entries: list[str] = []

    text = extract_text_from_capsule(None, FakeCapsule())
    assert "A Title" in text
    assert "A caption" in text


# ── resolve_target_modality ──────────────────────────────────────────


def test_resolve_explicit_modality() -> None:
    assert resolve_target_modality("twitter", "text_post") == "text_post"


def test_resolve_platform_default_twitter() -> None:
    assert resolve_target_modality("twitter", "") == "thread"


def test_resolve_platform_default_linkedin() -> None:
    assert resolve_target_modality("linkedin", "") == "text_post"


def test_resolve_unknown_platform_no_modality() -> None:
    with pytest.raises(WorkflowError, match="No default modality"):
        resolve_target_modality("instagram", "")


# ── validate_repurpose ───────────────────────────────────────────────


def test_validate_empty_text() -> None:
    with pytest.raises(WorkflowError, match="no text content"):
        validate_repurpose("", "text_post")


def test_validate_media_modality() -> None:
    with pytest.raises(WorkflowError, match="requires media generation"):
        validate_repurpose("Some text", "video")


def test_validate_success() -> None:
    validate_repurpose("Some text", "text_post")  # Should not raise
    validate_repurpose("Some text", "thread")  # Should not raise


# ── parse_repurpose_result ───────────────────────────────────────────


def test_parse_thread_result() -> None:
    raw = json.dumps({"thread_entries": ["First tweet", "Second tweet"]})
    result = parse_repurpose_result(raw, "thread")

    assert result["modality"] == "thread"
    assert result["thread_entries"] == ["First tweet", "Second tweet"]


def test_parse_text_post_result() -> None:
    raw = json.dumps({"body": "LinkedIn post body", "hashtags": ["AI", "edtech"]})
    result = parse_repurpose_result(raw, "text_post")

    assert result["modality"] == "text_post"
    assert result["caption"] == "LinkedIn post body"
    assert result["hashtags"] == ["AI", "edtech"]


def test_parse_dm_result() -> None:
    raw = json.dumps({"body": "Hey, check this out!"})
    result = parse_repurpose_result(raw, "direct_message")

    assert result["modality"] == "direct_message"
    assert result["caption"] == "Hey, check this out!"


def test_parse_with_markdown_fences() -> None:
    raw = '```json\n{"body": "Post text", "hashtags": []}\n```'
    result = parse_repurpose_result(raw, "text_post")

    assert result["caption"] == "Post text"


def test_parse_thread_missing_entries() -> None:
    raw = json.dumps({"something_else": "value"})
    with pytest.raises(ValueError, match="thread_entries"):
        parse_repurpose_result(raw, "thread")


def test_parse_text_post_missing_body() -> None:
    raw = json.dumps({"hashtags": ["test"]})
    with pytest.raises(ValueError, match="body"):
        parse_repurpose_result(raw, "text_post")


def test_parse_invalid_json() -> None:
    with pytest.raises(json.JSONDecodeError):
        parse_repurpose_result("not json", "text_post")


# ── CapsuleManager: derived_from + text_post ─────────────────────────


def test_capsule_derived_from(tmp_path: Path) -> None:
    root = tmp_path / "projects"
    mgr = CapsuleManager(projects_root=root)

    original = mgr.create("proj", "video", caption="original")
    derived = mgr.create(
        "proj",
        "text_post",
        caption="repurposed",
        derived_from=original.capsule_id,
    )

    assert derived.derived_from == original.capsule_id

    loaded = mgr.load("proj", derived.capsule_id)
    assert loaded.derived_from == original.capsule_id


def test_capsule_derived_from_default_empty(tmp_path: Path) -> None:
    root = tmp_path / "projects"
    mgr = CapsuleManager(projects_root=root)
    capsule = mgr.create("proj", "video", caption="test")
    assert capsule.derived_from == ""


def test_capsule_to_text_post(tmp_path: Path) -> None:
    root = tmp_path / "projects"
    mgr = CapsuleManager(projects_root=root)
    capsule = mgr.create(
        "proj",
        "text_post",
        caption="This is a great post about AI grading",
        hashtags=["AI", "edtech"],
    )
    from marketmenow.models.content import TextPost

    content = mgr.to_content(capsule, "proj")
    assert isinstance(content, TextPost)
    assert content.body == "This is a great post about AI grading"
    assert content.hashtags == ["AI", "edtech"]


def test_capsule_to_text_post_no_text(tmp_path: Path) -> None:
    root = tmp_path / "projects"
    mgr = CapsuleManager(projects_root=root)
    capsule = mgr.create("proj", "text_post")

    with pytest.raises(ValueError, match="no text content"):
        mgr.to_content(capsule, "proj")
