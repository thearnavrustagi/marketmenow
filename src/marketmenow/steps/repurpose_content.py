from __future__ import annotations

import json
import logging

from marketmenow.core.workflow import WorkflowContext, WorkflowError
from marketmenow.integrations.llm import LLMProvider, create_llm_provider

logger = logging.getLogger(__name__)

# Platform -> default target modality for text-based repurposing.
PLATFORM_DEFAULTS: dict[str, str] = {
    "twitter": "thread",
    "linkedin": "text_post",
    "reddit": "text_post",
    "facebook": "text_post",
    "email": "direct_message",
}

# Modalities that can be produced without media generation (text-only).
TEXT_MODALITIES = frozenset({"text_post", "thread", "direct_message"})

_SYSTEM_PROMPT = """\
You are a content repurposing assistant for social media marketing.
Your job is to take existing content and reformat it for a different platform and format.
Preserve the core message, tone, and call-to-action while adapting to the target format's conventions.
"""

_USER_PROMPT_TEMPLATE = """\
## Source Content
{source_text}

## Task
Repurpose this content for **{platform}** as a **{target_modality}**.

{format_instructions}

Return ONLY valid JSON, no markdown fences. The JSON schema:
{schema}
"""

_FORMAT_INSTRUCTIONS: dict[str, str] = {
    "thread": (
        "Break the content into a compelling Twitter/X thread of 3-8 tweets. "
        "First tweet should hook the reader. Use short, punchy sentences. "
        "Each tweet must be under 280 characters."
    ),
    "text_post": (
        "Write a single engaging post suitable for the platform. "
        "Include a hook, the main value, and a call-to-action. "
        "Keep it concise but informative."
    ),
    "direct_message": (
        "Write a short, personalised message that shares this content's key insight. "
        "Keep it conversational and under 500 characters."
    ),
}

_SCHEMAS: dict[str, str] = {
    "thread": '{"thread_entries": ["tweet 1 text", "tweet 2 text", ...]}',
    "text_post": '{"body": "the post text", "hashtags": ["tag1", "tag2"]}',
    "direct_message": '{"body": "the message text"}',
}


def extract_text_from_capsule(capsule_dir: str | None, capsule: object) -> str:
    """Extract all available text from a capsule for repurposing."""
    from pathlib import Path

    parts: list[str] = []

    # Get fields via attribute access (ContentCapsule is a Pydantic model)
    title = getattr(capsule, "title", "") or ""
    caption = getattr(capsule, "caption", "") or ""
    description = getattr(capsule, "description", "") or ""
    thread_entries: list[str] = getattr(capsule, "thread_entries", []) or []

    if title:
        parts.append(f"Title: {title}")
    if caption:
        parts.append(f"Caption: {caption}")
    if description:
        parts.append(f"Description: {description}")
    if thread_entries:
        parts.append("Thread:\n" + "\n---\n".join(thread_entries))

    # Check for script artifacts (generated scripts stored as JSON)
    if capsule_dir:
        script_dir = Path(capsule_dir) / "script"
        if script_dir.is_dir():
            for script_file in sorted(script_dir.glob("*.json")):
                try:
                    data = json.loads(script_file.read_text(encoding="utf-8"))
                    # Common script artifact fields
                    for key in ("script", "narration", "text", "story", "content"):
                        if key in data and isinstance(data[key], str):
                            parts.append(f"Script ({key}): {data[key]}")
                except Exception:
                    pass

    return "\n\n".join(parts)


def resolve_target_modality(platform: str, explicit_modality: str) -> str:
    """Determine target modality from explicit param or platform defaults."""
    if explicit_modality:
        return explicit_modality
    if platform in PLATFORM_DEFAULTS:
        return PLATFORM_DEFAULTS[platform]
    raise WorkflowError(
        f"No default modality for platform '{platform}'. "
        f"Specify --target-modality explicitly. Supported text modalities: {', '.join(sorted(TEXT_MODALITIES))}"
    )


def validate_repurpose(source_text: str, target_modality: str) -> None:
    """Validate that the repurpose operation is feasible."""
    if not source_text.strip():
        raise WorkflowError("Source capsule has no text content to repurpose")
    if target_modality not in TEXT_MODALITIES:
        raise WorkflowError(
            f"Target modality '{target_modality}' requires media generation (not yet supported). "
            f"Supported text modalities: {', '.join(sorted(TEXT_MODALITIES))}"
        )


def parse_repurpose_result(
    raw_text: str,
    target_modality: str,
) -> dict[str, str | list[str]]:
    """Parse LLM JSON output into capsule creation fields."""
    # Strip markdown fences if present
    text = raw_text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

    data = json.loads(text)

    match target_modality:
        case "thread":
            entries = data.get("thread_entries", [])
            if not entries or not isinstance(entries, list):
                raise ValueError("LLM response missing 'thread_entries' list")
            return {"thread_entries": entries, "modality": "thread"}
        case "text_post":
            body = data.get("body", "")
            if not body:
                raise ValueError("LLM response missing 'body'")
            hashtags = data.get("hashtags", [])
            return {"caption": body, "hashtags": hashtags, "modality": "text_post"}
        case "direct_message":
            body = data.get("body", "")
            if not body:
                raise ValueError("LLM response missing 'body'")
            return {"caption": body, "modality": "direct_message"}
        case _:
            raise ValueError(f"Unsupported target modality: {target_modality}")


class RepurposeContentStep:
    """Repurpose an existing capsule's content for a different platform/modality.

    Loads the source capsule, extracts text, calls the LLM to reformat,
    and creates a new derived capsule.
    """

    def __init__(self, provider: LLMProvider | None = None) -> None:
        self._provider = provider or create_llm_provider()

    @property
    def name(self) -> str:
        return "repurpose-content"

    @property
    def description(self) -> str:
        return "Repurpose capsule content for a different platform and format"

    async def execute(self, ctx: WorkflowContext) -> None:
        from marketmenow.core.capsule import CapsuleManager

        capsule_id = str(ctx.get_param("capsule", "") or "")
        if not capsule_id:
            raise WorkflowError("No capsule ID provided (--capsule)")

        project_slug = str(ctx.get_param("project", "") or "")
        if not project_slug and ctx.project:
            project_slug = ctx.project.slug
        if not project_slug:
            raise WorkflowError("No project slug available")

        platform = str(ctx.get_param("platform", "") or "")
        if not platform:
            raise WorkflowError("No target platform specified (--platform)")

        explicit_modality = str(ctx.get_param("target_modality", "") or "")
        target_modality = resolve_target_modality(platform, explicit_modality)

        mgr = CapsuleManager()
        capsule = mgr.load(project_slug, capsule_id)
        capsule_dir = str(mgr._capsule_dir(project_slug, capsule_id))

        source_text = extract_text_from_capsule(capsule_dir, capsule)
        validate_repurpose(source_text, target_modality)

        ctx.console.print(
            f"[bold blue]Repurposing capsule {capsule_id} "
            f"({capsule.modality}) -> {platform} ({target_modality})[/bold blue]"
        )

        format_instructions = _FORMAT_INSTRUCTIONS.get(target_modality, "")
        schema = _SCHEMAS.get(target_modality, "{}")
        user_prompt = _USER_PROMPT_TEMPLATE.format(
            source_text=source_text,
            platform=platform,
            target_modality=target_modality,
            format_instructions=format_instructions,
            schema=schema,
        )

        response = await self._provider.generate_text(
            model="",
            system=_SYSTEM_PROMPT,
            contents=user_prompt,
            temperature=0.8,
        )
        fields = parse_repurpose_result(response.text, target_modality)

        new_capsule = mgr.create(
            project_slug,
            modality=str(fields.get("modality", target_modality)),
            caption=str(fields.get("caption", "")),
            hashtags=list(fields.get("hashtags", [])),
            thread_entries=list(fields.get("thread_entries", [])),
            derived_from=capsule_id,
        )

        ctx.console.print(
            f"[green]Created derived capsule {new_capsule.capsule_id} "
            f"(derived from {capsule_id})[/green]"
        )
        ctx.set_artifact("capsule_id", new_capsule.capsule_id)
        ctx.set_artifact("derived_from", capsule_id)
