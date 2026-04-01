from __future__ import annotations

import json
import logging
import shutil
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import yaml
from pydantic import BaseModel, Field

from marketmenow.models.content import (
    BaseContent,
    ImagePost,
    MediaAsset,
    TextPost,
    Thread,
    ThreadEntry,
    VideoPost,
)

logger = logging.getLogger(__name__)


# ── Models ────────────────────────────────────────────────────────────


class CapsuleMediaEntry(BaseModel, frozen=True):
    """A media file stored inside a capsule directory."""

    path: str  # relative to capsule root, e.g. "media/reel.mp4"
    mime_type: str
    role: str = "primary"  # primary | thumbnail | slide


class CapsuleGenerationParams(BaseModel, frozen=True):
    """Original generation parameters for reproducing the content."""

    tts_provider: str = ""
    template_id: str = ""
    params: dict[str, str] = Field(default_factory=dict)


class CapsulePublication(BaseModel, frozen=True):
    """Record of a single publish event for this capsule."""

    platform: str
    published_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    remote_url: str = ""
    remote_post_id: str = ""


class ContentCapsule(BaseModel, frozen=True):
    """Self-contained content package with everything needed to post, repost, or regenerate."""

    capsule_id: str
    modality: str  # matches ContentModality values: video, image, thread, text_post
    template_id: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # Post metadata — platform-agnostic
    caption: str = ""
    title: str = ""
    description: str = ""
    hashtags: list[str] = Field(default_factory=list)
    privacy: str = ""

    # Media files (relative paths within capsule)
    media: list[CapsuleMediaEntry] = Field(default_factory=list)

    # Thread entries (for thread modality)
    thread_entries: list[str] = Field(default_factory=list)

    # Generation params for regeneration
    generation: CapsuleGenerationParams = Field(default_factory=CapsuleGenerationParams)

    # Publish history
    publications: list[CapsulePublication] = Field(default_factory=list)

    # Derivation tracking (capsule ID this was repurposed from)
    derived_from: str = ""

    # Tracking IDs
    reel_id_hex: str = ""
    template_type_hex: str = ""


# ── Manager ───────────────────────────────────────────────────────────


def _generate_capsule_id() -> str:
    """Generate a unique capsule ID: YYYYMMDD-HHMMSS-<hex6>."""
    now = datetime.now(UTC)
    hex_suffix = uuid4().hex[:6]
    return f"{now:%Y%m%d-%H%M%S}-{hex_suffix}"


class CapsuleManager:
    """CRUD operations for content capsules within a project.

    Capsules live under ``projects/{slug}/capsules/{capsule_id}/``.
    Each capsule directory contains a ``meta.yaml``, a ``media/`` subdirectory
    for asset files, and a ``script/`` subdirectory for generation artifacts.
    """

    def __init__(self, projects_root: Path | None = None) -> None:
        self._root = projects_root or Path("projects")

    def _capsule_dir(self, project_slug: str, capsule_id: str) -> Path:
        return self._root / project_slug / "capsules" / capsule_id

    def _write_meta(self, project_slug: str, capsule: ContentCapsule) -> Path:
        path = self._capsule_dir(project_slug, capsule.capsule_id) / "meta.yaml"
        data = json.loads(capsule.model_dump_json())
        # Convert datetime strings to proper format for YAML readability
        path.write_text(
            yaml.dump(data, default_flow_style=False, sort_keys=False),
            encoding="utf-8",
        )
        return path

    # ── create ────────────────────────────────────────────────────────

    def create(
        self,
        project_slug: str,
        modality: str,
        *,
        caption: str = "",
        title: str = "",
        description: str = "",
        hashtags: list[str] | None = None,
        privacy: str = "",
        template_id: str = "",
        generation: CapsuleGenerationParams | None = None,
        reel_id_hex: str = "",
        template_type_hex: str = "",
        thread_entries: list[str] | None = None,
        derived_from: str = "",
    ) -> ContentCapsule:
        capsule_id = _generate_capsule_id()
        capsule_dir = self._capsule_dir(project_slug, capsule_id)
        (capsule_dir / "media").mkdir(parents=True, exist_ok=True)
        (capsule_dir / "script").mkdir(parents=True, exist_ok=True)

        capsule = ContentCapsule(
            capsule_id=capsule_id,
            modality=modality,
            template_id=template_id,
            caption=caption,
            title=title,
            description=description,
            hashtags=hashtags or [],
            privacy=privacy,
            generation=generation or CapsuleGenerationParams(),
            reel_id_hex=reel_id_hex,
            template_type_hex=template_type_hex,
            thread_entries=thread_entries or [],
            derived_from=derived_from,
        )

        self._write_meta(project_slug, capsule)
        logger.info("Created capsule %s for project %s", capsule_id, project_slug)
        return capsule

    # ── load ──────────────────────────────────────────────────────────

    def load(self, project_slug: str, capsule_id: str) -> ContentCapsule:
        meta_path = self._capsule_dir(project_slug, capsule_id) / "meta.yaml"
        if not meta_path.exists():
            raise FileNotFoundError(f"Capsule '{capsule_id}' not found in project '{project_slug}'")
        raw = yaml.safe_load(meta_path.read_text(encoding="utf-8"))
        return ContentCapsule(**raw)

    def list_capsules(self, project_slug: str) -> list[ContentCapsule]:
        capsules_dir = self._root / project_slug / "capsules"
        if not capsules_dir.is_dir():
            return []
        results: list[ContentCapsule] = []
        for child in sorted(capsules_dir.iterdir()):
            meta = child / "meta.yaml"
            if meta.is_file():
                try:
                    raw = yaml.safe_load(meta.read_text(encoding="utf-8"))
                    results.append(ContentCapsule(**raw))
                except Exception:
                    logger.warning("Skipping invalid capsule at %s", child)
        return results

    # ── media management ──────────────────────────────────────────────

    def add_media(
        self,
        project_slug: str,
        capsule_id: str,
        source_path: Path,
        *,
        mime_type: str = "",
        role: str = "primary",
    ) -> CapsuleMediaEntry:
        capsule_dir = self._capsule_dir(project_slug, capsule_id)
        media_dir = capsule_dir / "media"
        media_dir.mkdir(parents=True, exist_ok=True)

        dest = media_dir / source_path.name
        if source_path.resolve() != dest.resolve():
            shutil.copy2(source_path, dest)

        if not mime_type:
            mime_type = _guess_mime(source_path)

        entry = CapsuleMediaEntry(
            path=f"media/{source_path.name}",
            mime_type=mime_type,
            role=role,
        )

        # Update meta.yaml
        capsule = self.load(project_slug, capsule_id)
        updated_media = list(capsule.media) + [entry]
        capsule = capsule.model_copy(update={"media": updated_media})
        self._write_meta(project_slug, capsule)

        return entry

    # ── script artifacts ──────────────────────────────────────────────

    def save_script_artifact(
        self,
        project_slug: str,
        capsule_id: str,
        name: str,
        data: dict[str, object],
    ) -> Path:
        script_dir = self._capsule_dir(project_slug, capsule_id) / "script"
        script_dir.mkdir(parents=True, exist_ok=True)
        path = script_dir / f"{name}.json"
        path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        return path

    # ── publication tracking ──────────────────────────────────────────

    def record_publication(
        self,
        project_slug: str,
        capsule_id: str,
        publication: CapsulePublication,
    ) -> None:
        capsule = self.load(project_slug, capsule_id)
        updated_pubs = list(capsule.publications) + [publication]
        capsule = capsule.model_copy(update={"publications": updated_pubs})
        self._write_meta(project_slug, capsule)

    # ── conversion to content models ──────────────────────────────────

    def to_content(
        self,
        capsule: ContentCapsule,
        project_slug: str,
    ) -> BaseContent:
        """Convert a capsule to the appropriate BaseContent subclass for publishing."""
        capsule_dir = self._capsule_dir(project_slug, capsule.capsule_id)

        match capsule.modality:
            case "video":
                return self._to_video_post(capsule, capsule_dir)
            case "image":
                return self._to_image_post(capsule, capsule_dir)
            case "thread":
                return self._to_thread(capsule)
            case "text_post":
                return self._to_text_post(capsule)
            case _:
                raise ValueError(f"Unsupported capsule modality: {capsule.modality}")

    def _to_video_post(
        self,
        capsule: ContentCapsule,
        capsule_dir: Path,
    ) -> VideoPost:
        primary = _find_media(capsule.media, "primary")
        if primary is None:
            raise ValueError(f"Capsule {capsule.capsule_id} has no primary media")

        video_path = capsule_dir / primary.path
        video_asset = MediaAsset(
            uri=str(video_path.resolve()),
            mime_type=primary.mime_type,
        )

        thumbnail_entry = _find_media(capsule.media, "thumbnail")
        thumbnail: MediaAsset | None = None
        if thumbnail_entry:
            thumb_path = capsule_dir / thumbnail_entry.path
            thumbnail = MediaAsset(
                uri=str(thumb_path.resolve()),
                mime_type=thumbnail_entry.mime_type,
            )

        # Build caption: use title + description if present (for YouTube-like platforms)
        caption = capsule.caption
        meta: dict[str, str] = {}
        if capsule.title:
            meta["_yt_title"] = capsule.title
        if capsule.description:
            meta["_yt_description"] = capsule.description
        if capsule.reel_id_hex:
            meta["_reel_id_bytes"] = capsule.reel_id_hex
        if capsule.template_type_hex:
            meta["_template_type_bytes"] = capsule.template_type_hex

        return VideoPost(
            video=video_asset,
            caption=caption,
            hashtags=capsule.hashtags,
            thumbnail=thumbnail,
            metadata=meta,
        )

    def _to_image_post(
        self,
        capsule: ContentCapsule,
        capsule_dir: Path,
    ) -> ImagePost:
        slide_entries = [m for m in capsule.media if m.role in ("primary", "slide")]
        if not slide_entries:
            raise ValueError(f"Capsule {capsule.capsule_id} has no image media")

        images = [
            MediaAsset(
                uri=str((capsule_dir / entry.path).resolve()),
                mime_type=entry.mime_type,
            )
            for entry in slide_entries
        ]

        return ImagePost(
            images=images,
            caption=capsule.caption,
            hashtags=capsule.hashtags,
        )

    @staticmethod
    def _to_thread(capsule: ContentCapsule) -> Thread:
        if not capsule.thread_entries:
            raise ValueError(f"Capsule {capsule.capsule_id} has no thread entries")

        return Thread(
            entries=[ThreadEntry(text=text) for text in capsule.thread_entries],
        )

    @staticmethod
    def _to_text_post(capsule: ContentCapsule) -> TextPost:
        body = capsule.caption or capsule.description or capsule.title
        if not body:
            raise ValueError(f"Capsule {capsule.capsule_id} has no text content for text_post")

        return TextPost(
            body=body,
            hashtags=capsule.hashtags,
        )


# ── Helpers ───────────────────────────────────────────────────────────


def _find_media(
    entries: list[CapsuleMediaEntry],
    role: str,
) -> CapsuleMediaEntry | None:
    for entry in entries:
        if entry.role == role:
            return entry
    return None


_MIME_MAP: dict[str, str] = {
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".wav": "audio/wav",
    ".mp3": "audio/mpeg",
}


def _guess_mime(path: Path) -> str:
    return _MIME_MAP.get(path.suffix.lower(), "application/octet-stream")
