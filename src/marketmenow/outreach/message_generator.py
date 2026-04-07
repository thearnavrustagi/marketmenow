from __future__ import annotations

import logging

from marketmenow.integrations.llm import LLMProvider, create_llm_provider
from marketmenow.outreach.models import (
    CustomerProfile,
    OutreachMessage,
    ScoredProspect,
)

logger = logging.getLogger(__name__)


class OutreachMessageGenerator:
    """Generates personalised outreach messages. Platform-agnostic."""

    def __init__(
        self,
        model: str = "gemini-2.5-flash",
        provider: LLMProvider | None = None,
    ) -> None:
        self._provider = provider or create_llm_provider()
        self._model = model

    async def generate(
        self,
        prospect: ScoredProspect,
        customer_profile: CustomerProfile,
    ) -> OutreachMessage:
        from marketmenow.core.prompt_builder import PromptBuilder

        profile = prospect.user_profile
        ref_post_text = profile.triggering_posts[0] if profile.triggering_posts else ""
        ref_post_url = profile.triggering_post_urls[0] if profile.triggering_post_urls else ""

        built = PromptBuilder().build(
            platform="outreach",
            function="generate_message",
            template_vars={
                "product": customer_profile.product,
                "messaging": customer_profile.messaging,
                "handle": profile.handle,
                "bio": profile.bio,
                "dm_angle": prospect.dm_angle,
                "reference_post": customer_profile.messaging.reference_post,
                "triggering_post_text": ref_post_text,
                "triggering_post_url": ref_post_url,
            },
        )

        response = await self._provider.generate_text(
            model=self._model,
            system=built.system,
            contents=built.user,
            temperature=1.0,
        )
        message_text = response.text.strip().strip('"').strip("'")

        if not message_text:
            raise ValueError(f"LLM returned empty response for @{profile.handle}")

        return OutreachMessage(
            recipient_handle=profile.handle,
            message_text=message_text,
            referenced_post_url=ref_post_url,
            referenced_post_text=ref_post_text,
            prospect_score=prospect.total_score,
            dm_angle=prospect.dm_angle,
        )
