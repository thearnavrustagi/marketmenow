from __future__ import annotations

from pathlib import Path

import yaml

from marketmenow.models.project import BrandConfig, PersonaConfig, TargetCustomer


def generate_twitter_prompt(brand: BrandConfig, persona: PersonaConfig) -> str:
    """Return a persona YAML for the Twitter platform.

    The function-specific templates (reply, thread) live in the global
    ``prompts/twitter/functions/`` directory.  This generates the
    project-scoped **persona** file that defines *who* the account is.
    """
    phrases_items = _bullet_list(
        [f'"{p}"' for p in persona.example_phrases],
        fallback='"(no examples yet)"',
    )

    system_lines = [
        "You ARE {{ brand.name }}. You're the social media personality behind",
        "{{ brand.tagline }}.",
        "You are NOT a corporate account - you are a CHARACTER with a real voice.",
        "",
        "YOUR PERSONALITY:",
        f"- {persona.description}" if persona.description else "- (describe personality here)",
        f"- Voice: {persona.voice}" if persona.voice else "- Voice: (describe voice here)",
        f"- Tone: {persona.tone}" if persona.tone else "- Tone: (describe tone here)",
        "- Example phrases:",
        *phrases_items,
        "- You NEVER sound like a PR team or a marketing playbook",
        "- Keeps replies SHORT (under 250 characters ideally, 280 max)",
        "",
        "WHAT YOU KNOW (but rarely say outright):",
        "- You're {{ brand.url }} - {{ brand.tagline }}",
        "{% for feat in brand.features %}",
        "- {{ feat }}",
        "{% endfor %}",
    ]

    return _build_prompt_yaml(system_lines, [])


def generate_reddit_prompt(brand: BrandConfig, persona: PersonaConfig) -> str:
    """Return a persona YAML for the Reddit platform.

    The function-specific template (comment) lives in the global
    ``prompts/reddit/functions/`` directory.
    """
    system_lines = [
        "You are a helpful, knowledgeable community member on Reddit.",
        "You are NOT a brand account. You are a real person who happens to",
        "have experience with {{ brand.url }} - {{ brand.tagline }}.",
        "",
        "YOUR PERSONA:",
        f"- {persona.description}" if persona.description else "- (describe persona here)",
        f"- Voice: {persona.voice}" if persona.voice else "- Voice: (describe voice here)",
        f"- Tone: {persona.tone}" if persona.tone else "- Tone: (describe tone here)",
        "- You give practical, specific advice",
        "- You write like a real Redditor: conversational, no corporate polish",
        "",
        "WHAT YOU KNOW (but rarely say outright):",
        "- You're connected to {{ brand.url }} - {{ brand.tagline }}",
        "{% for feat in brand.features %}",
        "- {{ feat }}",
        "{% endfor %}",
    ]

    return _build_prompt_yaml(system_lines, [])


def generate_instagram_prompt(brand: BrandConfig, persona: PersonaConfig) -> str:
    """Return a YAML prompt file (system + user) for Instagram reel script generation."""
    features_items = _bullet_list(brand.features, fallback="(no features listed)")
    phrases_items = _bullet_list(
        [f'"{p}"' for p in persona.example_phrases],
        fallback='"(no examples yet)"',
    )

    system_lines = [
        f"You are a short-form video script writer for {brand.name}.",
        "",
        "BRAND",
        f"Name: {brand.name}",
        f"URL: {brand.url}",
        f"Tagline: {brand.tagline}",
        "Features:",
        *features_items,
        "",
        "VOICE / CHARACTERS",
        f"Primary persona: {persona.name}",
        persona.description,
        f"Voice: {persona.voice}",
        f"Tone: {persona.tone}",
        "Example phrases:",
        *phrases_items,
        "",
        "SCRIPT RULES",
        "- Every text field you return becomes TTS audio — keep each to 1-2 sentences.",
        "- The hook must grab attention in under 2 seconds.",
        "- End with a clear CTA (follow, visit URL, comment).",
        "- Return valid JSON with exactly the fields requested.",
        "- No markdown, no explanation — just the JSON object.",
    ]

    user_lines = [
        "TEMPLATE: {{ template_name }}",
        "",
        "Generate a reel script. Return a JSON object with these fields:",
        "{% for field in output_fields -%}",
        "- {{ field }}",
        "{% endfor %}",
        "Each value should be a short string (1-2 sentences max) suitable for",
        "text-to-speech narration.",
    ]

    return _build_prompt_yaml(system_lines, user_lines)


def generate_twitter_targets(
    influencers: list[str],
    hashtags: list[str],
    companies: list[str],
) -> str:
    """Return a YAML targets file for the Twitter engagement workflow."""
    data = {
        "influencers": influencers,
        "hashtags": hashtags,
        "company_accounts": companies,
    }
    return yaml.dump(data, default_flow_style=False, sort_keys=False)


def generate_reddit_targets(
    subreddits: list[str],
    queries: list[str],
) -> str:
    """Return a YAML targets file for the Reddit engagement workflow."""
    data = {
        "subreddits": subreddits,
        "search_queries": queries,
    }
    return yaml.dump(data, default_flow_style=False, sort_keys=False)


def generate_outreach_campaign(
    brand: BrandConfig,
    customer: TargetCustomer,
    rubric: list[dict[str, object]],
    discovery: list[dict[str, object]],
    messaging: dict[str, object],
) -> str:
    """Return a YAML campaign file matching the CustomerProfile schema."""
    data: dict[str, object] = {
        "platform": "twitter",
        "product": {
            "name": brand.name,
            "url": brand.url,
            "tagline": brand.tagline,
            "value_prop": brand.value_prop,
        },
        "ideal_customer": {
            "description": customer.description,
            "rubric": [
                {
                    "name": r.get("name", ""),
                    "description": r.get("description", ""),
                    "max_points": r.get("max_points", 3),
                }
                for r in rubric
            ],
            "min_score": 8,
            "max_prospects_to_enrich": 50,
        },
        "discovery": [
            {
                "type": d.get("type", "pain_search"),
                "entries": d.get("entries", []),
                "max_per_entry": d.get("max_per_entry", 5),
            }
            for d in discovery
        ],
        "messaging": messaging,
    }
    return yaml.dump(data, default_flow_style=False, sort_keys=False)


def generate_reddit_campaign(brand: BrandConfig) -> str:
    """Return a Reddit launch campaign YAML with product info and placeholder subreddits."""
    data: dict[str, object] = {
        "product": {
            "name": brand.name,
            "url": brand.url,
            "description": brand.tagline,
        },
        "subreddits": [
            "buildinpublic",
            "microsaas",
            "SaaSDevelopers",
        ],
        "post_type": "update",
        "context": "",
        "posting": {
            "min_delay": 120,
            "max_delay": 300,
        },
    }
    return yaml.dump(data, default_flow_style=False, sort_keys=False)


def generate_reel_meta_prompt(brand: BrandConfig, customer: TargetCustomer) -> str:
    """Pre-fill the reels meta-prompt template with actual brand values.

    Reads ``src/adapters/instagram/reels/templates/prompt.md`` relative to
    this module's location and replaces placeholder tokens.
    """
    core_dir = Path(__file__).resolve().parent
    src_dir = core_dir.parent.parent
    template_path = src_dir / "adapters" / "instagram" / "reels" / "templates" / "prompt.md"

    content = template_path.read_text(encoding="utf-8")

    suffix = brand.logo_suffix or ""
    content = content.replace("[YOUR BRAND NAME]", brand.name)
    content = content.replace('[e.g. ".ai", ".app", ".io", ""]', f'"{suffix}"')
    content = content.replace('[e.g. "#FF6B35"]', f'"{brand.color}"')
    content = content.replace('[e.g. "cookbot.app"]', f'"{brand.url}"')

    what_it_does = brand.tagline
    if brand.value_prop:
        what_it_does += f" — {brand.value_prop}"
    content = content.replace(
        '[one sentence — e.g. "AI recipe generator that turns fridge photos into meals"]',
        f'"{what_it_does}"',
    )

    audience = customer.description
    content = content.replace(
        '[e.g. "home cooks, college students, busy parents"]',
        f'"{audience}"',
    )

    return content


# ── internal helpers ──────────────────────────────────────────────────


def _bullet_list(items: list[str], *, fallback: str = "(none)") -> list[str]:
    """Return a list of ``'- item'`` strings, or a single fallback bullet."""
    if items:
        return [f"- {item}" for item in items]
    return [f"- {fallback}"]


def _indent(text: str, spaces: int) -> str:
    """Indent every line of *text* by *spaces* spaces.

    Empty lines are preserved as truly empty (no trailing spaces) which is
    valid inside YAML block scalars.
    """
    prefix = " " * spaces
    return "\n".join(prefix + line if line else "" for line in text.splitlines())


def _build_prompt_yaml(system_lines: list[str], user_lines: list[str]) -> str:
    """Assemble a ``system: | ... user: | ...`` YAML document from line lists."""
    system_body = _indent("\n".join(system_lines), 2)
    user_body = _indent("\n".join(user_lines), 2)
    return f"system: |\n{system_body}\n\nuser: |\n{user_body}\n"
