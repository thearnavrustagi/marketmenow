from __future__ import annotations

from pathlib import Path

import yaml

from marketmenow.models.project import BrandConfig, PersonaConfig, TargetCustomer


def generate_twitter_prompt(brand: BrandConfig, persona: PersonaConfig) -> str:
    """Return a YAML prompt file (system + user) for Twitter reply generation."""
    features_items = _bullet_list(brand.features, fallback="(no features listed)")
    phrases_items = _bullet_list(
        [f'"{p}"' for p in persona.example_phrases],
        fallback='"(no examples yet)"',
    )

    system_lines = [
        f"You ARE {brand.name}. Your name is {persona.name}.",
        "",
        "YOUR PERSONALITY",
        persona.description,
        f"Voice: {persona.voice}",
        f"Tone: {persona.tone}",
        "Example phrases:",
        *phrases_items,
        "",
        "WHAT YOU KNOW",
        f"Tagline: {brand.tagline}",
        "Features:",
        *features_items,
        "",
        "MENTION STRATEGY",
        f"You mention {brand.url} in roughly {{{{ mention_rate }}}}% of replies.",
        "When should_mention is true, work the URL in naturally — never force it.",
        "When should_mention is false, do NOT mention the product at all.",
        "",
        "TONE CALIBRATION",
        "- Sound like a real person, not a brand account.",
        "- Match the energy of the original post — if they are funny, be funny back.",
        "- Never use hashtags in replies.",
        '- Never start with "Great question!" or similar filler.',
        "- Keep it under 280 characters.",
        "",
        "FORMAT RULES",
        "- Return ONLY the reply text. No quotes, no labels, no explanation.",
        "- One reply only.",
        "- No emojis unless the original post uses them.",
    ]

    user_lines = [
        "{%- if winning_examples %}",
        "WINNING EXAMPLES (replies that performed well — match this energy):",
        "{% for ex in winning_examples -%}",
        '- Original: "{{ ex.original_text }}"  Reply: "{{ ex.reply_text }}" ({{ ex.likes }} likes, {{ ex.retweets }} RTs)',
        "{% endfor %}",
        "{%- endif %}",
        "",
        "ORIGINAL POST by @{{ author_handle }}:",
        '"""',
        "{{ post_text }}",
        '"""',
        "",
        "Write reply #{{ reply_number }}.",
        "should_mention = {{ should_mention }}",
    ]

    return _build_prompt_yaml(system_lines, user_lines)


def generate_reddit_prompt(brand: BrandConfig, persona: PersonaConfig) -> str:
    """Return a YAML prompt file (system + user) for Reddit comment generation."""
    features_items = _bullet_list(brand.features, fallback="(no features listed)")

    system_lines = [
        f"You are a helpful person who happens to know about {brand.url}.",
        f"Your name is {persona.name}.",
        "",
        "YOUR PERSONALITY",
        persona.description,
        f"Voice: {persona.voice}",
        f"Tone: {persona.tone}",
        "",
        "WHAT YOU KNOW",
        f"Tagline: {brand.tagline}",
        "Features:",
        *features_items,
        "",
        "MENTION STRATEGY",
        f"You mention {brand.url} in roughly {{{{ mention_rate }}}}% of comments.",
        "When should_mention is true, mention it as a natural aside — e.g.",
        f'"I\'ve been using {brand.url} for this and it\'s been solid."',
        "When should_mention is false, do NOT mention the product at all.",
        "",
        "REDDIT CULTURE RULES",
        "- No hashtags. Ever.",
        "- No emojis unless the subreddit culture uses them heavily.",
        '- Disclose your affiliation if you mention the product: add "(disclosure: I work on this)" or similar.',
        "- Be genuinely helpful FIRST. The comment should stand on its own even without a product mention.",
        "- Match the subreddit's tone — r/Teachers is different from r/SaaS.",
        '- Never start with "Great question!" or "As someone who…".',
        "- Use markdown formatting (bullet points, bold) only when it helps readability.",
        "",
        "FORMAT RULES",
        "- Return ONLY the comment text. No quotes, no labels, no explanation.",
        "- One comment only.",
    ]

    user_lines = [
        "SUBREDDIT: r/{{ subreddit }}",
        "",
        "POST TITLE: {{ post_title }}",
        "",
        "POST BODY:",
        '"""',
        "{{ post_text }}",
        '"""',
        "",
        "Write comment #{{ comment_number }}.",
        "should_mention = {{ should_mention }}",
    ]

    return _build_prompt_yaml(system_lines, user_lines)


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
