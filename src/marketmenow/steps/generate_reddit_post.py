from __future__ import annotations

import os
from pathlib import Path

from marketmenow.core.workflow import WorkflowContext, WorkflowError


def _load_campaign_config(config_path: str) -> dict[str, object]:
    """Load a YAML campaign config file and return its contents."""
    import yaml

    path = Path(config_path)
    if not path.exists():
        raise WorkflowError(f"Config file not found: {config_path}")

    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    return data  # type: ignore[return-value]


def _read_brief(value: str) -> str:
    """If *value* is a path to an existing file, read it; otherwise return as-is."""
    path = Path(value)
    if path.exists() and path.is_file():
        return path.read_text(encoding="utf-8").strip()
    return value


class GenerateRedditPostStep:
    """Generate a Reddit post (update/milestone/launch) for each target subreddit.

    Reads product info from either CLI params or a YAML config file
    (``--config``). Accepts ``--brief`` for raw content the AI should
    adapt (blog draft, release notes, rough notes — inline text or a
    file path).
    """

    @property
    def name(self) -> str:
        return "generate-reddit-posts"

    @property
    def description(self) -> str:
        return "Generate Reddit posts via AI for each subreddit"

    async def execute(self, ctx: WorkflowContext) -> None:
        from adapters.reddit.post_generator import RedditPostGenerator
        from adapters.reddit.settings import RedditSettings

        settings = RedditSettings()

        creds = settings.google_application_credentials
        if creds and creds.exists():
            os.environ.setdefault("GOOGLE_APPLICATION_CREDENTIALS", str(creds.resolve()))

        if not settings.vertex_ai_project:
            raise WorkflowError("VERTEX_AI_PROJECT not set in .env")

        config_path = ctx.get_param("config")
        cfg: dict[str, object] = {}
        if config_path:
            cfg = _load_campaign_config(str(config_path))
            ctx.console.print(f"  [dim]Loaded config from {config_path}[/dim]")

        product_cfg = cfg.get("product", {}) if isinstance(cfg.get("product"), dict) else {}

        product_name = str(
            ctx.get_param("product_name") or product_cfg.get("name", "")  # type: ignore[union-attr]
        )
        product_url = str(
            ctx.get_param("product_url")
            or product_cfg.get("url", "")  # type: ignore[union-attr]
            or ""
        )
        product_description = str(
            ctx.get_param("product_description") or product_cfg.get("description", "")  # type: ignore[union-attr]
        )
        post_type = str(ctx.get_param("post_type") or cfg.get("post_type", "update") or "update")

        if not product_name:
            raise WorkflowError("product_name is required (via --product-name or config YAML)")
        if not product_description:
            raise WorkflowError(
                "product_description is required (via --product-description or config YAML)"
            )

        cfg_subs = cfg.get("subreddits", [])
        subs_param = str(ctx.get_param("subreddits", "") or "")
        if subs_param:
            subreddits = [s.strip() for s in subs_param.split(",") if s.strip()]
        elif isinstance(cfg_subs, list):
            subreddits = [str(s) for s in cfg_subs]
        else:
            subreddits = []

        if not subreddits:
            raise WorkflowError("No subreddits specified (via --subreddits or config YAML)")

        extra_context = str(ctx.get_param("context") or cfg.get("context", "") or "")

        brief_raw = str(ctx.get_param("brief", "") or "")
        brief = _read_brief(brief_raw) if brief_raw else ""

        if brief:
            brief_block = (
                f"\n\nSOURCE MATERIAL (adapt this into a Reddit post, "
                f'don\'t copy verbatim):\n"""\n{brief}\n"""'
            )
            extra_context = extra_context + brief_block if extra_context else brief_block.strip()

        posting_cfg = cfg.get("posting", {}) if isinstance(cfg.get("posting"), dict) else {}
        if posting_cfg:
            if "min_delay" not in ctx.params and "min_delay" in posting_cfg:
                ctx.params["min_delay"] = int(posting_cfg["min_delay"])  # type: ignore[arg-type]
            if "max_delay" not in ctx.params and "max_delay" in posting_cfg:
                ctx.params["max_delay"] = int(posting_cfg["max_delay"])  # type: ignore[arg-type]

        generator = RedditPostGenerator(
            model=settings.gemini_model,
            persona=ctx.persona,
            brand=ctx.project.brand if ctx.project else None,
            project_slug=ctx.project.slug if ctx.project else None,
            top_examples_path=settings.top_examples_path,
            max_examples=settings.max_examples_in_prompt,
            epsilon=settings.epsilon,
        )

        posts = []
        for sub in subreddits:
            ctx.console.print(f"  [dim]Generating post for r/{sub}...[/dim]")
            post = await generator.generate_post(
                subreddit=sub,
                product_name=product_name,
                product_url=product_url,
                product_description=product_description,
                post_type=post_type,
                context=extra_context,
            )
            posts.append(post)
            ctx.console.print(f"  [green]r/{sub}:[/green] {post.title}")

        ctx.console.print(f"\n[green]Generated {len(posts)} posts[/green]")
        ctx.set_artifact("reddit_posts", posts)
