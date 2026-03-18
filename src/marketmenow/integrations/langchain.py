"""LangChain tool wrappers for MarketMeNow.

Install the optional dependency group to use these tools:

    uv sync --extra langchain

Then bind them to any LangChain-compatible agent:

    from marketmenow.integrations.langchain import get_tools
    tools = get_tools(registry)
    agent = create_agent(model=..., tools=tools)
"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING

from langchain_core.tools import tool

from marketmenow.models.campaign import Campaign, CampaignTarget
from marketmenow.models.content import (
    Article,
    BaseContent,
    ContentModality,
    DirectMessage,
    Document,
    ImagePost,
    Poll,
    Reply,
    TextPost,
    Thread,
    VideoPost,
)

if TYPE_CHECKING:
    from langchain_core.tools import BaseTool

    from marketmenow.registry import AdapterRegistry

_registry: AdapterRegistry | None = None


def _get_registry() -> AdapterRegistry:
    if _registry is None:
        raise RuntimeError(
            "MarketMeNow registry not initialised. "
            "Call marketmenow.integrations.langchain.init(registry) first, "
            "or use get_tools(registry) which does this automatically."
        )
    return _registry


def init(registry: AdapterRegistry) -> None:
    """Bind a live AdapterRegistry so the LangChain tools can operate."""
    global _registry
    _registry = registry


def _build_content(modality: str, payload: dict[str, object]) -> BaseContent:
    """Deserialise a JSON payload into the appropriate content model."""
    match modality:
        case "video":
            return VideoPost(**payload)
        case "image":
            return ImagePost(**payload)
        case "thread":
            return Thread(**payload)
        case "direct_message":
            return DirectMessage(**payload)
        case "reply":
            return Reply(**payload)
        case "text_post":
            return TextPost(**payload)
        case "document":
            return Document(**payload)
        case "article":
            return Article(**payload)
        case "poll":
            return Poll(**payload)
        case _:
            raise ValueError(f"Unknown modality: {modality}")


@tool
def mmn_list_platforms() -> str:
    """List all registered marketing platforms and the content modalities they support.

    Returns a JSON object mapping platform names to lists of supported modality strings.
    Use this to discover which platforms are available before publishing.
    """
    registry = _get_registry()
    result: dict[str, list[str]] = {}
    for name in registry.list_platforms():
        bundle = registry.get(name)
        result[name] = [m.value for m in bundle.adapter.supported_modalities()]
    return json.dumps(result, indent=2)


@tool
def mmn_publish(platform: str, modality: str, content_json: str) -> str:
    """Publish a single piece of content to a marketing platform.

    Args:
        platform: Target platform name (e.g. "instagram", "twitter").
        modality: Content type — one of "video", "image", "thread",
                  "direct_message", "reply", "text_post", "document",
                  or "article".
        content_json: JSON string with the content fields. For a video this
                      includes "video" (with "uri" and "mime_type"),
                      "caption", and "hashtags". For an image: "images",
                      "caption", "hashtags". See the MarketMeNow docs for
                      the full schema per modality.

    Returns:
        JSON string with the publish or send result.
    """
    from marketmenow.core.pipeline import ContentPipeline

    registry = _get_registry()
    payload = json.loads(content_json)
    content = _build_content(modality, payload)

    pipeline = ContentPipeline(registry)
    result = asyncio.run(pipeline.execute(content, platform))
    return result.model_dump_json(indent=2)


@tool
def mmn_run_campaign(campaign_json: str) -> str:
    """Run a multi-platform marketing campaign.

    Args:
        campaign_json: JSON string representing a Campaign object with
                       "name", "content" (including a "modality" field),
                       and "targets" (list of {"platform", "modality"}).

    Returns:
        JSON summary with publish results and any errors.
    """
    from marketmenow.core.orchestrator import Orchestrator

    registry = _get_registry()

    raw = json.loads(campaign_json)
    content_data = raw.pop("content", {})
    modality = content_data.get("modality", "")
    content = _build_content(modality, content_data)

    targets = [
        CampaignTarget(
            platform=t["platform"],
            modality=ContentModality(t["modality"]),
        )
        for t in raw.get("targets", [])
    ]

    campaign = Campaign(
        name=raw.get("name", "LangChain Campaign"),
        content=content,
        targets=targets,
    )

    orchestrator = Orchestrator(registry)
    result = asyncio.run(orchestrator.run_campaign(campaign))

    return json.dumps(
        {
            "campaign_id": str(result.campaign_id),
            "results": [r.model_dump(mode="json") for r in result.results],
            "errors": [{"target": str(t), "error": str(e)} for t, e in result.errors],
        },
        indent=2,
    )


def get_tools(registry: AdapterRegistry) -> list[BaseTool]:
    """Return all MarketMeNow LangChain tools, initialised with the given registry.

    Usage::

        from marketmenow.integrations.langchain import get_tools
        from marketmenow import AdapterRegistry

        registry = AdapterRegistry()
        # ... register platform bundles ...
        tools = get_tools(registry)
    """
    init(registry)
    return [mmn_list_platforms, mmn_publish, mmn_run_campaign]
