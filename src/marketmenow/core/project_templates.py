from __future__ import annotations

from pathlib import Path

import yaml

from marketmenow.models.project import BrandConfig, PersonaConfig, TargetCustomer

_TEMPLATES_DIR = Path(__file__).resolve().parents[3] / "prompts" / "templates"


def _load_template(name: str) -> str:
    """Read a YAML template from ``prompts/templates/`` and return its raw text."""
    path = _TEMPLATES_DIR / f"{name}.yaml"
    return path.read_text(encoding="utf-8")


def generate_twitter_prompt(brand: BrandConfig, persona: PersonaConfig) -> str:
    """Return a persona YAML for the Twitter platform.

    Loads from ``prompts/templates/twitter_persona.yaml`` and fills in
    brand-specific persona values. The result is written to the project's
    ``prompts/twitter/persona.yaml`` during onboarding.
    """
    raw = _load_template("twitter_persona")
    phrases_block = "\n".join(
        _bullet_list(
            [f'"{p}"' for p in persona.example_phrases],
            fallback='"(no examples yet)"',
        )
    )
    return _fill_persona_vars(raw, persona, phrases_block)


def generate_reddit_prompt(brand: BrandConfig, persona: PersonaConfig) -> str:
    """Return a persona YAML for the Reddit platform.

    Loads from ``prompts/templates/reddit_persona.yaml``.
    """
    raw = _load_template("reddit_persona")
    return _fill_persona_vars(raw, persona, "")


def generate_instagram_prompt(brand: BrandConfig, persona: PersonaConfig) -> str:
    """Return a YAML prompt file (system + user) for Instagram reel script generation.

    Loads from ``prompts/templates/instagram_script.yaml`` and fills in
    brand-specific values. The Jinja2 variables (``{{ brand.name }}``, etc.)
    are left intact for runtime rendering.
    """
    raw = _load_template("instagram_script")
    features_block = "\n".join(
        "  " + line if line.strip() else ""
        for line in "\n".join(
            _bullet_list(brand.features, fallback="(no features listed)")
        ).splitlines()
    )
    phrases_block = "\n".join(
        "  " + line if line.strip() else ""
        for line in "\n".join(
            _bullet_list(
                [f'"{p}"' for p in persona.example_phrases],
                fallback='"(no examples yet)"',
            )
        ).splitlines()
    )
    replacements = {
        "{{ brand_name }}": brand.name,
        "{{ brand_url }}": brand.url,
        "{{ brand_tagline }}": brand.tagline,
        "{{ features_block }}": features_block,
        "{{ persona_name }}": persona.name,
        "{{ persona_description }}": persona.description,
        "{{ persona_voice }}": persona.voice,
        "{{ persona_tone }}": persona.tone,
        "{{ phrases_block }}": phrases_block,
    }
    for token, value in replacements.items():
        raw = raw.replace(token, value)
    return raw


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


def generate_default_generation_config(platforms: list[str]) -> str:
    """Return a default generation_config.yaml based on selected platforms."""
    items = []

    if "instagram" in platforms:
        items.append({"platform": "instagram", "command_type": "reel", "count": 2})
        items.append({"platform": "instagram", "command_type": "carousel", "count": 2})
        # If Instagram is present, assume YouTube Shorts as well
        if "youtube" not in platforms:
            platforms.append("youtube")

    if "twitter" in platforms:
        items.append({"platform": "twitter", "command_type": "thread"})
        items.append({"platform": "twitter", "command_type": "engage"})
        items.append(
            {
                "platform": "twitter",
                "command_type": "outreach",
                "params": {"profile": "campaigns/twitter-outreach.yaml"},
            }
        )

    if "linkedin" in platforms:
        items.append({"platform": "linkedin", "command_type": "post"})

    if "facebook" in platforms:
        items.append({"platform": "facebook", "command_type": "post"})

    if "reddit" in platforms:
        items.append({"platform": "reddit", "command_type": "engage"})

    if "youtube" in platforms:
        items.append({"platform": "youtube", "command_type": "short", "count": 2})

    if "email" in platforms:
        items.append({"platform": "email", "command_type": "send"})

    return yaml.dump({"items": items}, default_flow_style=False, sort_keys=False)


# ── internal helpers ──────────────────────────────────────────────────


def _bullet_list(items: list[str], *, fallback: str = "(none)") -> list[str]:
    """Return a list of ``'- item'`` strings, or a single fallback bullet."""
    if items:
        return [f"- {item}" for item in items]
    return [f"- {fallback}"]


def _fill_persona_vars(raw: str, persona: PersonaConfig, phrases_block: str) -> str:
    """Replace persona placeholder tokens in a template YAML string.

    ``phrases_block`` lines are indented to match the surrounding YAML block
    scalar indentation (2 spaces) so ``- "..."`` items don't break parsing.
    """
    indented_phrases = "\n".join(
        "  " + line if line.strip() else "" for line in phrases_block.splitlines()
    )
    replacements = {
        "{{ persona_description }}": persona.description or "(describe personality here)",
        "{{ persona_voice }}": persona.voice or "(describe voice here)",
        "{{ persona_tone }}": persona.tone or "(describe tone here)",
        "{{ phrases_block }}": indented_phrases,
    }
    for token, value in replacements.items():
        raw = raw.replace(token, value)
    return raw
