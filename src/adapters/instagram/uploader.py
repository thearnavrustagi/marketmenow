from __future__ import annotations

import logging
import mimetypes
from pathlib import Path
from uuid import uuid4

import boto3
from botocore.config import Config

from marketmenow.models.content import MediaAsset
from marketmenow.models.result import MediaRef

logger = logging.getLogger(__name__)


class InstagramUploader:
    """Satisfies ``Uploader`` protocol.

    Uploads local media files to an S3 bucket and returns presigned URLs
    that Instagram's servers can fetch during container creation.

    The presigned URLs default to 1-hour expiry which is more than enough
    for Instagram to ingest the media.
    """

    def __init__(
        self,
        bucket: str,
        region: str = "us-east-1",
        prefix: str = "instagram/uploads",
        presign_expires: int = 3600,
        aws_access_key_id: str = "",
        aws_secret_access_key: str = "",
    ) -> None:
        self._bucket = bucket
        self._prefix = prefix.strip("/")
        self._presign_expires = presign_expires

        session_kwargs: dict[str, str] = {}
        if aws_access_key_id and aws_secret_access_key:
            session_kwargs["aws_access_key_id"] = aws_access_key_id
            session_kwargs["aws_secret_access_key"] = aws_secret_access_key

        session = boto3.Session(region_name=region, **session_kwargs)  # type: ignore[arg-type]
        self._s3 = session.client("s3", config=Config(signature_version="s3v4"))

    @property
    def platform_name(self) -> str:
        return "instagram"

    async def upload(self, asset: MediaAsset) -> MediaRef:
        src = Path(asset.uri)
        if not src.exists():
            return MediaRef(platform="instagram", remote_id="", remote_url=asset.uri)

        key = f"{self._prefix}/{uuid4().hex}{src.suffix}"
        content_type = mimetypes.guess_type(src.name)[0] or "application/octet-stream"

        self._s3.upload_file(
            str(src),
            self._bucket,
            key,
            ExtraArgs={"ContentType": content_type},
        )
        logger.info("Uploaded %s -> s3://%s/%s", src.name, self._bucket, key)

        url: str = self._s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket, "Key": key},
            ExpiresIn=self._presign_expires,
        )

        return MediaRef(platform="instagram", remote_id=key, remote_url=url)

    async def upload_batch(self, assets: list[MediaAsset]) -> list[MediaRef]:
        return [await self.upload(a) for a in assets]
