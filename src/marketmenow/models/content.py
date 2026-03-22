from __future__ import annotations

import enum
from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class ContentModality(str, enum.Enum):
    VIDEO = "video"
    IMAGE = "image"
    THREAD = "thread"
    DIRECT_MESSAGE = "direct_message"
    REPLY = "reply"
    TEXT_POST = "text_post"
    DOCUMENT = "document"
    ARTICLE = "article"
    POLL = "poll"


class MediaAsset(BaseModel, frozen=True):
    """A single media file reference -- local path or remote URL."""

    uri: str
    mime_type: str
    alt_text: str = ""
    duration_seconds: float | None = None
    width: int | None = None
    height: int | None = None


class BaseContent(BaseModel, frozen=True):
    """Abstract base for all content modalities."""

    id: UUID = Field(default_factory=uuid4)
    modality: ContentModality
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, str] = Field(default_factory=dict)


class VideoPost(BaseContent):
    """A video post (Instagram Reel, LinkedIn video, etc.)."""

    modality: ContentModality = ContentModality.VIDEO
    video: MediaAsset
    caption: str = ""
    hashtags: list[str] = Field(default_factory=list)
    thumbnail: MediaAsset | None = None


class ImagePost(BaseContent):
    """A post with one or more images (single image, carousel, multi-image)."""

    modality: ContentModality = ContentModality.IMAGE
    images: list[MediaAsset] = Field(..., min_length=1)
    caption: str = ""
    hashtags: list[str] = Field(default_factory=list)


class ThreadEntry(BaseModel, frozen=True):
    text: str
    media: list[MediaAsset] = Field(default_factory=list)


class Thread(BaseContent):
    modality: ContentModality = ContentModality.THREAD
    entries: list[ThreadEntry] = Field(..., min_length=1)


class Recipient(BaseModel, frozen=True):
    handle: str
    platform_id: str | None = None


class DirectMessage(BaseContent):
    modality: ContentModality = ContentModality.DIRECT_MESSAGE
    recipients: list[Recipient] = Field(..., min_length=1)
    subject: str | None = None
    body: str
    attachments: list[MediaAsset] = Field(default_factory=list)


class Reply(BaseContent):
    """A reply to an existing post on any platform."""

    modality: ContentModality = ContentModality.REPLY
    in_reply_to_url: str
    in_reply_to_platform_id: str | None = None
    body: str
    media: list[MediaAsset] = Field(default_factory=list)


class TextPost(BaseContent):
    """A standalone text post (e.g. LinkedIn thought-leadership update)."""

    modality: ContentModality = ContentModality.TEXT_POST
    body: str
    hashtags: list[str] = Field(default_factory=list)


class Document(BaseContent):
    """A document upload (PDF, PPT, DOCX) -- used for LinkedIn document carousels."""

    modality: ContentModality = ContentModality.DOCUMENT
    file: MediaAsset
    title: str = ""
    caption: str = ""
    hashtags: list[str] = Field(default_factory=list)


class Article(BaseContent):
    """A link-share / article post with optional commentary."""

    modality: ContentModality = ContentModality.ARTICLE
    url: str
    commentary: str = ""
    hashtags: list[str] = Field(default_factory=list)


class Poll(BaseContent):
    """A poll post with a question and 2-4 answer options."""

    modality: ContentModality = ContentModality.POLL
    question: str
    options: list[str] = Field(..., min_length=2, max_length=4)
    duration_days: int = Field(default=3, ge=1, le=14)
    commentary: str = ""
    hashtags: list[str] = Field(default_factory=list)
