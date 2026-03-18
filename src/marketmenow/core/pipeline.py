from __future__ import annotations

from marketmenow.models.content import BaseContent, ContentModality
from marketmenow.models.result import MediaRef, PublishResult, SendResult
from marketmenow.normaliser import ContentNormaliser, NormalisedContent
from marketmenow.registry import AdapterRegistry


class ContentPipeline:
    def __init__(self, registry: AdapterRegistry) -> None:
        self._registry = registry
        self._normaliser = ContentNormaliser()

    async def execute(self, content: BaseContent, platform: str) -> PublishResult | SendResult:
        bundle = self._registry.get(platform)

        normalised: NormalisedContent = self._normaliser.normalise(content)

        rendered: NormalisedContent = await bundle.renderer.render(normalised)

        media_refs: list[MediaRef] = await bundle.uploader.upload_batch(rendered.media_assets)
        rendered = rendered.model_copy(
            update={"extra": {**rendered.extra, "_media_refs": media_refs}}
        )

        if content.modality == ContentModality.DIRECT_MESSAGE:
            return await bundle.adapter.send_dm(rendered)
        return await bundle.adapter.publish(rendered)
