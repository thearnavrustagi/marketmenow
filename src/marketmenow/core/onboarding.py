from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel

from marketmenow.core.project_manager import ProjectManager
from marketmenow.core.project_templates import (
    generate_instagram_prompt,
    generate_outreach_campaign,
    generate_reddit_prompt,
    generate_reddit_targets,
    generate_reel_meta_prompt,
    generate_twitter_prompt,
    generate_twitter_targets,
)
from marketmenow.models.project import (
    BrandConfig,
    PersonaConfig,
    TargetCustomer,
)


@dataclass
class OnboardingResult:
    brand: BrandConfig
    target_customer: TargetCustomer
    persona: PersonaConfig
    twitter_targets_created: bool = False
    reddit_targets_created: bool = False
    outreach_profile_created: bool = False
    prompts_created: list[str] = field(default_factory=list)
    reel_templates: list[str] = field(default_factory=list)
    files_created: list[Path] = field(default_factory=list)
    set_as_active: bool = False


# ── helpers ──────────────────────────────────────────────────────────────


def _collect_lines(console: Console, label: str) -> list[str]:
    """Prompt for lines one at a time until empty input."""
    items: list[str] = []
    while True:
        val = typer.prompt(f"  {label}", default="", show_default=False)
        if not val:
            break
        items.append(val)
    return items


def _read_until_sentinel(sentinel: str = "END") -> str:
    """Read lines from stdin without echoing until sentinel line is seen."""
    lines: list[str] = []
    while True:
        line = sys.stdin.readline()
        if not line or line.strip() == sentinel:
            break
        lines.append(line)
    return "".join(lines)


def _phase_header(console: Console, number: int, title: str) -> None:
    console.print()
    console.print(Panel(f"[bold]Phase {number}/10[/bold] — {title}", style="cyan"))


# ── phase 1: brand identity ─────────────────────────────────────────────


def _phase_brand(console: Console) -> BrandConfig:
    _phase_header(console, 1, "Brand Identity")

    name = typer.prompt("Brand name")
    url = typer.prompt("Website URL")
    tagline = typer.prompt("Tagline")
    value_prop = typer.prompt("Value proposition (one sentence)", default="")
    color = typer.prompt("Brand color (hex)", default="#000000")
    logo_letter = typer.prompt("Logo letter", default=name[0].upper() if name else "")
    logo_suffix = typer.prompt("Logo suffix (e.g. '.ai', 'HQ')", default="")

    return BrandConfig(
        name=name,
        url=url,
        tagline=tagline,
        value_prop=value_prop,
        color=color,
        logo_letter=logo_letter,
        logo_suffix=logo_suffix,
    )


# ── phase 2: product features ───────────────────────────────────────────


def _phase_features(console: Console) -> list[str]:
    _phase_header(console, 2, "Product Features")
    console.print("  Enter features one per line. Leave blank to finish.")
    return _collect_lines(console, "Feature")


# ── phase 3: target customer ────────────────────────────────────────────


def _phase_target_customer(console: Console) -> TargetCustomer:
    _phase_header(console, 3, "Target Customer")

    description = typer.prompt("Describe your ideal customer (one sentence)")

    console.print("  Pain points (one per line, blank to finish):")
    pain_points = _collect_lines(console, "Pain point")

    console.print("  Keywords / topics (one per line, blank to finish):")
    keywords = _collect_lines(console, "Keyword")

    platforms_raw = typer.prompt(
        "Platforms (comma-separated, e.g. twitter,reddit,instagram)",
        default="twitter,reddit,instagram",
    )
    platforms = [p.strip().lower() for p in platforms_raw.split(",") if p.strip()]

    return TargetCustomer(
        description=description,
        pain_points=pain_points,
        keywords=keywords,
        platforms=platforms,
    )


# ── phase 4: social media persona ───────────────────────────────────────


def _phase_persona(console: Console) -> PersonaConfig:
    _phase_header(console, 4, "Social Media Persona")

    name = typer.prompt("Persona name", default="default")
    description = typer.prompt("Brief description", default="")
    voice = typer.prompt("Voice style (e.g. 'witty and concise')", default="")
    tone = typer.prompt("Tone (e.g. 'friendly, professional')", default="")

    console.print("  Example phrases (one per line, blank to finish):")
    example_phrases = _collect_lines(console, "Phrase")

    return PersonaConfig(
        name=name,
        description=description,
        voice=voice,
        tone=tone,
        example_phrases=example_phrases,
    )


# ── phase 5: twitter targets ────────────────────────────────────────────


def _phase_twitter_targets(
    console: Console,
    pm: ProjectManager,
    slug: str,
    files: list[Path],
) -> bool:
    _phase_header(console, 5, "Twitter Targets")

    if not typer.confirm("Set up Twitter targets?", default=True):
        return False

    console.print("  Influencer handles (one per line, prefix with @, blank to finish):")
    influencers = _collect_lines(console, "@handle")

    console.print("  Hashtags (one per line, prefix with #, blank to finish):")
    hashtags = _collect_lines(console, "#hashtag")

    console.print("  Company accounts to monitor (one per line, blank to finish):")
    companies = _collect_lines(console, "Account")

    content = generate_twitter_targets(influencers, hashtags, companies)
    path = pm.save_file(slug, "targets", "twitter.yaml", content=content)
    files.append(path)
    console.print(f"  [green]✓[/green] Saved {path}")
    return True


# ── phase 6: reddit targets ─────────────────────────────────────────────


def _phase_reddit_targets(
    console: Console,
    pm: ProjectManager,
    slug: str,
    keywords: list[str],
    files: list[Path],
) -> bool:
    _phase_header(console, 6, "Reddit Targets")

    if not typer.confirm("Set up Reddit targets?", default=True):
        return False

    console.print("  Subreddits (one per line, blank to finish):")
    subreddits = _collect_lines(console, "r/subreddit")

    if keywords:
        console.print(f"  [dim]Suggested queries from keywords: {', '.join(keywords)}[/dim]")
    console.print("  Search queries (one per line, blank to finish):")
    queries = _collect_lines(console, "Query")

    content = generate_reddit_targets(subreddits, queries)
    path = pm.save_file(slug, "targets", "reddit.yaml", content=content)
    files.append(path)
    console.print(f"  [green]✓[/green] Saved {path}")
    return True


# ── phase 7: outreach profile ───────────────────────────────────────────


def _phase_outreach(
    console: Console,
    pm: ProjectManager,
    slug: str,
    brand: BrandConfig,
    customer: TargetCustomer,
    files: list[Path],
) -> bool:
    _phase_header(console, 7, "Outreach Profile")

    if not typer.confirm("Set up outreach profile?", default=True):
        return False

    console.print("  Define scoring rubric criteria:")
    rubric: list[dict[str, str | int]] = []
    while True:
        crit_name = typer.prompt("  Criterion name")
        crit_desc = typer.prompt("  Criterion description")
        crit_max = typer.prompt("  Max points", default="10")
        rubric.append({"name": crit_name, "description": crit_desc, "max_points": int(crit_max)})
        if not typer.confirm("  Add another criterion?", default=False):
            break

    min_score_raw = typer.prompt("  Minimum score to reach out", default="15")

    discovery_vectors = [{"query": kw, "type": "keyword"} for kw in customer.keywords]
    if discovery_vectors:
        console.print("  [dim]Auto-generated discovery vectors from keywords:[/dim]")
        for dv in discovery_vectors:
            console.print(f"    • {dv['query']}")
        typer.confirm("  Use these discovery vectors?", default=True)

    messaging_tone = typer.prompt("  Messaging tone", default="friendly and professional")
    max_messages = typer.prompt("  Max messages per session", default="10")
    max_msg_len = typer.prompt("  Max message length (chars)", default="280")

    messaging = {
        "tone": messaging_tone,
        "max_messages": int(max_messages),
        "max_message_length": int(max_msg_len),
        "min_score": int(min_score_raw),
    }

    content = generate_outreach_campaign(
        brand, customer, rubric, discovery_vectors, messaging
    )
    path = pm.save_file(slug, "campaigns", "twitter-outreach.yaml", content=content)
    files.append(path)
    console.print(f"  [green]✓[/green] Saved {path}")
    return True


# ── phase 8: platform prompts ───────────────────────────────────────────


_PROMPT_GENERATORS: dict[str, tuple[str, object]] = {}


def _phase_prompts(
    console: Console,
    pm: ProjectManager,
    slug: str,
    brand: BrandConfig,
    persona: PersonaConfig,
    platforms: list[str],
    files: list[Path],
) -> list[str]:
    _phase_header(console, 8, "Platform Prompts")

    generators: dict[str, tuple[str, object]] = {
        "twitter": ("prompts/twitter/reply_generation.yaml", generate_twitter_prompt),
        "reddit": ("prompts/reddit/comment_generation.yaml", generate_reddit_prompt),
        "instagram": ("prompts/instagram/script_generation.yaml", generate_instagram_prompt),
    }

    created: list[str] = []
    for platform in platforms:
        if platform not in generators:
            continue

        rel_path, gen_fn = generators[platform]
        if not typer.confirm(f"Generate starter prompt for {platform}?", default=True):
            continue

        content = gen_fn(brand, persona)
        parts = rel_path.split("/")
        path = pm.save_file(slug, *parts, content=content)
        files.append(path)
        created.append(platform)
        console.print(f"  [green]✓[/green] Saved {path}")

    return created


# ── phase 9: reel templates ─────────────────────────────────────────────


def _phase_reel_templates(
    console: Console,
    pm: ProjectManager,
    slug: str,
    brand: BrandConfig,
    customer: TargetCustomer,
    files: list[Path],
) -> list[str]:
    _phase_header(console, 9, "Reel Templates")

    meta_prompt = generate_reel_meta_prompt(brand, customer)
    meta_path = pm.save_file(
        slug, "templates", "reels", "REEL_TEMPLATE_PROMPT.md", content=meta_prompt
    )
    files.append(meta_path)
    console.print(f"  [green]✓[/green] Saved meta-prompt to {meta_path}")

    if not typer.confirm("Set up a reel template?", default=True):
        console.print("  [dim]You can use the meta-prompt later to create templates.[/dim]")
        return []

    console.print(f"  Open [bold]{meta_path}[/bold], fill in your concept,")
    console.print("  then paste the result into ChatGPT/Claude to generate the YAML template.")

    templates_created: list[str] = []
    while True:
        typer.prompt("  Press Enter when ready to paste a template", default="", show_default=False)

        template_id = typer.prompt("  Template ID (e.g. 'product-demo')")

        console.print("  Paste the YAML template below. Type [bold]END[/bold] on its own line when done:")
        yaml_content = _read_until_sentinel("END")

        path = pm.save_reel_template(slug, template_id, yaml_content)
        files.append(path)
        templates_created.append(template_id)
        console.print(f"  [green]✓[/green] Saved template to {path}")

        try:
            from adapters.instagram.reels.template_loader import ReelTemplateLoader

            loader = ReelTemplateLoader(templates_dir=path.parent)
            issues = loader.validate(template_id)
            if issues:
                console.print("  [yellow]⚠ Validation warnings:[/yellow]")
                for issue in issues:
                    console.print(f"    • {issue}")
            else:
                console.print("  [green]✓[/green] Template validated successfully")
        except Exception:
            console.print("  [dim]Skipped validation (Instagram adapter not available)[/dim]")

        if not typer.confirm("  Add another template?", default=False):
            break

    return templates_created


# ── phase 10: summary & activation ──────────────────────────────────────


def _phase_summary(
    console: Console,
    pm: ProjectManager,
    slug: str,
    result: OnboardingResult,
) -> None:
    _phase_header(console, 10, "Summary & Activation")

    brand = result.brand
    display_name = brand.name
    if brand.logo_suffix:
        display_name += brand.logo_suffix

    summary_lines = [
        f"[bold]Project:[/bold] {slug}",
        f"[bold]Brand:[/bold] {display_name}  [dim]({brand.color})[/dim]",
        f"[bold]Customer:[/bold] {result.target_customer.description}",
        f"[bold]Persona:[/bold] {result.persona.name}",
    ]
    console.print(Panel("\n".join(summary_lines), title="Project Summary", style="green"))

    categories: dict[str, list[Path]] = {
        "CORE": [],
        "TARGETING": [],
        "PROMPTS": [],
        "TEMPLATES": [],
    }
    for f in result.files_created:
        parts_str = str(f)
        if "targets/" in parts_str or "campaigns/" in parts_str:
            categories["TARGETING"].append(f)
        elif "prompts/" in parts_str:
            categories["PROMPTS"].append(f)
        elif "templates/" in parts_str:
            categories["TEMPLATES"].append(f)
        else:
            categories["CORE"].append(f)

    console.print("\n[bold]Created files:[/bold]")
    for cat, cat_files in categories.items():
        if not cat_files:
            continue
        console.print(f"  [cyan]{cat}[/cyan]")
        for f in cat_files:
            console.print(f"    • {f}")

    result.set_as_active = typer.confirm("\nSet as active project?", default=True)
    if result.set_as_active:
        pm.set_active_project(slug)
        console.print(f"  [green]✓[/green] Active project set to [bold]{slug}[/bold]")

    console.print()
    console.print(Panel(
        "\n".join([
            "[bold]What's Next[/bold]",
            "",
            f"  mmn run twitter-engage --project {slug}",
            f"  mmn run reddit-engage --project {slug}",
            f"  mmn run instagram-reel --project {slug}",
            f"  mmn run twitter-outreach --project {slug}",
            "",
            "  mmn workflows            — list all available workflows",
            "  mmn-web                  — open the web dashboard",
        ]),
        style="blue",
    ))


# ── main entry point ────────────────────────────────────────────────────


def run_onboarding(
    pm: ProjectManager | None = None,
    console: Console | None = None,
    slug_override: str = "",
) -> OnboardingResult:
    """Run the interactive 10-phase onboarding wizard."""
    if console is None:
        console = Console()
    if pm is None:
        pm = ProjectManager()

    console.print(Panel(
        "[bold]MarketMeNow Project Setup[/bold]\n"
        "Create a new marketing project in 10 easy steps.",
        style="magenta",
    ))

    # Phase 1 — Brand
    brand = _phase_brand(console)

    # Phase 2 — Features
    features = _phase_features(console)
    brand = brand.model_copy(update={"features": features})

    # Phase 3 — Target customer
    customer = _phase_target_customer(console)

    # Phase 4 — Persona
    persona = _phase_persona(console)

    slug = slug_override or brand.name.lower().replace(" ", "-")
    pm.create_project(
        slug,
        brand,
        target_customer=customer,
        default_persona=persona.name,
    )
    pm.save_persona(slug, persona)

    files: list[Path] = [
        pm.project_dir(slug) / "project.yaml",
        pm.project_dir(slug) / "personas" / f"{persona.name}.yaml",
    ]

    result = OnboardingResult(
        brand=brand,
        target_customer=customer,
        persona=persona,
        files_created=files,
    )

    # Phase 5 — Twitter targets
    if "twitter" in customer.platforms:
        result.twitter_targets_created = _phase_twitter_targets(
            console, pm, slug, files
        )

    # Phase 6 — Reddit targets
    if "reddit" in customer.platforms:
        result.reddit_targets_created = _phase_reddit_targets(
            console, pm, slug, customer.keywords, files
        )

    # Phase 7 — Outreach profile
    if "twitter" in customer.platforms:
        result.outreach_profile_created = _phase_outreach(
            console, pm, slug, brand, customer, files
        )

    # Phase 8 — Platform prompts
    result.prompts_created = _phase_prompts(
        console, pm, slug, brand, persona, customer.platforms, files
    )

    # Phase 9 — Reel templates
    if "instagram" in customer.platforms:
        result.reel_templates = _phase_reel_templates(
            console, pm, slug, brand, customer, files
        )

    # Phase 10 — Summary & activation
    _phase_summary(console, pm, slug, result)

    return result
