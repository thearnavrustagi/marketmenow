from __future__ import annotations

from pathlib import Path

import pytest

from marketmenow.core.capsule import (
    CapsuleGenerationParams,
    CapsuleManager,
    CapsulePublication,
)
from marketmenow.models.content import ImagePost, Thread, VideoPost

# ── CapsuleManager CRUD ──────────────────────────────────────────────


def test_capsule_create_and_load(tmp_path: Path) -> None:
    root = tmp_path / "projects"
    (root / "testproj" / "capsules").mkdir(parents=True)
    mgr = CapsuleManager(projects_root=root)

    capsule = mgr.create(
        "testproj",
        "video",
        caption="Hello world",
        hashtags=["AI", "test"],
        template_id="can_ai_grade_this",
    )

    assert capsule.capsule_id
    assert capsule.modality == "video"
    assert capsule.caption == "Hello world"
    assert capsule.hashtags == ["AI", "test"]

    # meta.yaml should exist
    meta_path = root / "testproj" / "capsules" / capsule.capsule_id / "meta.yaml"
    assert meta_path.exists()

    # Load it back
    loaded = mgr.load("testproj", capsule.capsule_id)
    assert loaded.capsule_id == capsule.capsule_id
    assert loaded.caption == "Hello world"
    assert loaded.hashtags == ["AI", "test"]


def test_capsule_add_media(tmp_path: Path) -> None:
    root = tmp_path / "projects"
    (root / "testproj" / "capsules").mkdir(parents=True)
    mgr = CapsuleManager(projects_root=root)

    capsule = mgr.create("testproj", "video", caption="test")

    # Create a fake video file
    video_file = tmp_path / "reel.mp4"
    video_file.write_bytes(b"\x00" * 100)

    entry = mgr.add_media(
        "testproj",
        capsule.capsule_id,
        video_file,
        mime_type="video/mp4",
        role="primary",
    )

    assert entry.path == "media/reel.mp4"
    assert entry.mime_type == "video/mp4"
    assert entry.role == "primary"

    # File should be copied
    copied = root / "testproj" / "capsules" / capsule.capsule_id / "media" / "reel.mp4"
    assert copied.exists()
    assert copied.read_bytes() == b"\x00" * 100

    # meta.yaml should have the media entry
    loaded = mgr.load("testproj", capsule.capsule_id)
    assert len(loaded.media) == 1
    assert loaded.media[0].role == "primary"


def test_capsule_record_publication(tmp_path: Path) -> None:
    root = tmp_path / "projects"
    (root / "testproj" / "capsules").mkdir(parents=True)
    mgr = CapsuleManager(projects_root=root)

    capsule = mgr.create("testproj", "video", caption="test")

    mgr.record_publication(
        "testproj",
        capsule.capsule_id,
        CapsulePublication(
            platform="instagram",
            remote_url="https://instagram.com/reel/abc",
            remote_post_id="abc123",
        ),
    )

    loaded = mgr.load("testproj", capsule.capsule_id)
    assert len(loaded.publications) == 1
    assert loaded.publications[0].platform == "instagram"
    assert loaded.publications[0].remote_url == "https://instagram.com/reel/abc"

    # Add another publication
    mgr.record_publication(
        "testproj",
        capsule.capsule_id,
        CapsulePublication(
            platform="youtube",
            remote_url="https://youtube.com/shorts/xyz",
            remote_post_id="xyz789",
        ),
    )

    loaded = mgr.load("testproj", capsule.capsule_id)
    assert len(loaded.publications) == 2
    assert loaded.publications[1].platform == "youtube"


def test_capsule_save_script_artifact(tmp_path: Path) -> None:
    root = tmp_path / "projects"
    (root / "testproj" / "capsules").mkdir(parents=True)
    mgr = CapsuleManager(projects_root=root)

    capsule = mgr.create("testproj", "video")

    path = mgr.save_script_artifact(
        "testproj",
        capsule.capsule_id,
        "reel_script",
        {"template_id": "test", "fps": 30, "beats": []},
    )

    assert path.exists()
    assert path.name == "reel_script.json"


def test_capsule_list(tmp_path: Path) -> None:
    root = tmp_path / "projects"
    (root / "testproj" / "capsules").mkdir(parents=True)
    mgr = CapsuleManager(projects_root=root)

    mgr.create("testproj", "video", caption="first")
    mgr.create("testproj", "image", caption="second")
    mgr.create("testproj", "thread", caption="third")

    capsules = mgr.list_capsules("testproj")
    assert len(capsules) == 3


def test_capsule_list_empty(tmp_path: Path) -> None:
    root = tmp_path / "projects"
    mgr = CapsuleManager(projects_root=root)

    capsules = mgr.list_capsules("nonexistent")
    assert capsules == []


def test_capsule_load_not_found(tmp_path: Path) -> None:
    root = tmp_path / "projects"
    (root / "testproj" / "capsules").mkdir(parents=True)
    mgr = CapsuleManager(projects_root=root)

    with pytest.raises(FileNotFoundError):
        mgr.load("testproj", "nonexistent-id")


# ── Conversion to content models ─────────────────────────────────────


def test_capsule_to_video_post(tmp_path: Path) -> None:
    root = tmp_path / "projects"
    (root / "testproj" / "capsules").mkdir(parents=True)
    mgr = CapsuleManager(projects_root=root)

    capsule = mgr.create(
        "testproj",
        "video",
        caption="Watch this!",
        title="My Video",
        hashtags=["AI"],
        reel_id_hex="a1b2c3",
    )

    # Add a video file
    video_file = tmp_path / "reel.mp4"
    video_file.write_bytes(b"\x00" * 50)
    mgr.add_media("testproj", capsule.capsule_id, video_file, role="primary")

    capsule = mgr.load("testproj", capsule.capsule_id)
    content = mgr.to_content(capsule, "testproj")

    assert isinstance(content, VideoPost)
    assert content.caption == "Watch this!"
    assert content.hashtags == ["AI"]
    assert content.metadata["_yt_title"] == "My Video"
    assert content.metadata["_reel_id_bytes"] == "a1b2c3"


def test_capsule_to_image_post(tmp_path: Path) -> None:
    root = tmp_path / "projects"
    (root / "testproj" / "capsules").mkdir(parents=True)
    mgr = CapsuleManager(projects_root=root)

    capsule = mgr.create(
        "testproj",
        "image",
        caption="Carousel!",
        hashtags=["design"],
    )

    # Add image files
    for i, role in enumerate(["primary", "slide", "slide"]):
        img = tmp_path / f"slide_{i}.png"
        img.write_bytes(b"\x89PNG" + b"\x00" * 50)
        mgr.add_media("testproj", capsule.capsule_id, img, role=role)

    capsule = mgr.load("testproj", capsule.capsule_id)
    content = mgr.to_content(capsule, "testproj")

    assert isinstance(content, ImagePost)
    assert content.caption == "Carousel!"
    assert len(content.images) == 3


def test_capsule_to_thread(tmp_path: Path) -> None:
    root = tmp_path / "projects"
    (root / "testproj" / "capsules").mkdir(parents=True)
    mgr = CapsuleManager(projects_root=root)

    capsule = mgr.create(
        "testproj",
        "thread",
        thread_entries=["Tweet 1", "Tweet 2", "Tweet 3"],
    )

    content = mgr.to_content(capsule, "testproj")

    assert isinstance(content, Thread)
    assert len(content.entries) == 3
    assert content.entries[0].text == "Tweet 1"


def test_capsule_to_content_unsupported_modality(tmp_path: Path) -> None:
    root = tmp_path / "projects"
    (root / "testproj" / "capsules").mkdir(parents=True)
    mgr = CapsuleManager(projects_root=root)

    capsule = mgr.create("testproj", "poll")

    with pytest.raises(ValueError, match="Unsupported capsule modality"):
        mgr.to_content(capsule, "testproj")


def test_capsule_to_video_post_no_media(tmp_path: Path) -> None:
    root = tmp_path / "projects"
    (root / "testproj" / "capsules").mkdir(parents=True)
    mgr = CapsuleManager(projects_root=root)

    capsule = mgr.create("testproj", "video")

    with pytest.raises(ValueError, match="no primary media"):
        mgr.to_content(capsule, "testproj")


def test_capsule_to_thread_no_entries(tmp_path: Path) -> None:
    root = tmp_path / "projects"
    (root / "testproj" / "capsules").mkdir(parents=True)
    mgr = CapsuleManager(projects_root=root)

    capsule = mgr.create("testproj", "thread")

    with pytest.raises(ValueError, match="no thread entries"):
        mgr.to_content(capsule, "testproj")


# ── Generation params ─────────────────────────────────────────────────


def test_capsule_generation_params(tmp_path: Path) -> None:
    root = tmp_path / "projects"
    (root / "testproj" / "capsules").mkdir(parents=True)
    mgr = CapsuleManager(projects_root=root)

    gen = CapsuleGenerationParams(
        tts_provider="kokoro",
        template_id="can_ai_grade_this",
        params={"assignment": "/path/to/file.png"},
    )

    capsule = mgr.create(
        "testproj",
        "video",
        generation=gen,
    )

    loaded = mgr.load("testproj", capsule.capsule_id)
    assert loaded.generation.tts_provider == "kokoro"
    assert loaded.generation.template_id == "can_ai_grade_this"
    assert loaded.generation.params["assignment"] == "/path/to/file.png"
