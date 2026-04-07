from __future__ import annotations

import json
import logging
from datetime import date

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from marketmenow.core.campaign_manager import CampaignManager
from marketmenow.core.project_manager import ProjectManager
from marketmenow.core.workflow_registry import build_workflow_registry
from marketmenow.integrations.llm import LLMProvider, create_llm_provider
from marketmenow.models.campaign_plan import CampaignPlan

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a marketing campaign strategist. You help plan multi-platform social media campaigns.

## Your role
- Analyze the brand, product, and target customer information provided
- Suggest an opinionated campaign plan with specific dates, platforms, content types, and topics
- Be creative but practical — each item must map to an available workflow

## Available workflows (you MUST only use these):
{workflows}

## Project context:
Brand: {brand_name} — {brand_tagline}
URL: {brand_url}
Target customer: {target_customer}

## Rules
1. Each calendar item needs: id, date (YYYY-MM-DD), platform, workflow (exact name from list above), content_type, topic, brief, cta
2. Start dates from {start_date}
3. Repurpose chains: when a reel can be cross-posted (e.g., instagram-reel -> youtube-short via post-capsule)
4. Be specific in briefs — give the AI enough context to generate good content
5. Use a mix of content types across platforms for variety
6. When the user says "done" or "looks good", output the FINAL plan as JSON matching this schema:

```json
{{
  "name": "campaign-slug",
  "goal": {{"objective": "...", "kpi": "...", "duration_days": N}},
  "audience_summary": "...",
  "tone": "...",
  "platforms": ["instagram", "twitter", ...],
  "calendar": [
    {{"id": "day1-reel", "date": "YYYY-MM-DD", "platform": "instagram", "workflow": "instagram-reel", "content_type": "reel", "topic": "...", "brief": "...", "cta": "..."}}
  ],
  "repurpose_chains": [
    {{"source_item_id": "day1-reel", "target_items": ["day2-youtube"]}}
  ]
}}
```

Start by proposing a campaign plan based on the project context. Be opinionated — present a concrete plan, don't just ask questions.
"""


class CampaignPlanner:
    """Interactive terminal chatbot that plans campaigns via LLM conversation."""

    def __init__(
        self,
        provider: LLMProvider | None = None,
        project_manager: ProjectManager | None = None,
    ) -> None:
        self._provider = provider or create_llm_provider()
        self._pm = project_manager or ProjectManager()
        self._manager = CampaignManager(self._pm)

    async def plan(
        self,
        project_slug: str,
        console: Console | None = None,
    ) -> CampaignPlan:
        """Run the interactive campaign planning conversation."""
        console = console or Console()

        project = self._pm.load_project(project_slug)
        brand = project.brand

        # Build available workflows list
        registry = build_workflow_registry()
        workflows_desc = "\n".join(
            f"- {name}: {wf.description}" for name, wf in sorted(registry._workflows.items())
        )

        system = _SYSTEM_PROMPT.format(
            workflows=workflows_desc,
            brand_name=brand.name,
            brand_tagline=brand.tagline,
            brand_url=brand.url,
            target_customer=project.target_customer.description
            if project.target_customer
            else "Not specified",
            start_date=date.today().isoformat(),
        )

        history: list[dict[str, str]] = []

        console.print(
            Panel(
                f"[bold cyan]Campaign Planner[/bold cyan] for [bold]{brand.name}[/bold]\n"
                f"Platforms available: {', '.join(name for name in registry._workflows)}\n\n"
                "I'll propose a campaign plan. Refine it, then type [bold]done[/bold] to finalize.",
                title="Campaign Planner",
            )
        )

        # First turn: LLM proposes an opinionated plan
        response = await self._provider.generate_text(
            model="",
            system=system,
            contents="Propose a campaign plan for this brand. Be specific and opinionated.",
            temperature=0.9,
        )
        assistant_msg = response.text
        history.append({"role": "user", "content": "Propose a campaign plan for this brand."})
        history.append({"role": "assistant", "content": assistant_msg})

        console.print()
        console.print(Markdown(assistant_msg))
        console.print()

        # Conversation loop
        while True:
            try:
                user_input = console.input("[bold green]You>[/bold green] ").strip()
            except (EOFError, KeyboardInterrupt):
                console.print("\n[yellow]Campaign planning cancelled.[/yellow]")
                raise KeyboardInterrupt from None

            if not user_input:
                continue

            history.append({"role": "user", "content": user_input})

            # Check if user wants to finalize
            is_done = user_input.lower() in ("done", "looks good", "finalize", "confirm", "yes")

            if is_done:
                prompt = (
                    "The user has confirmed the plan. Output the FINAL campaign plan as JSON only. "
                    "No markdown fences, no explanation — just the raw JSON object."
                )
            else:
                prompt = user_input

            # Build conversation context
            context_parts = [
                "Previous conversation:\n"
                + "\n".join(
                    f"{'User' if m['role'] == 'user' else 'Assistant'}: {m['content'][:500]}"
                    for m in history[:-1]
                ),
                f"\nUser's latest message: {prompt}",
            ]

            response = await self._provider.generate_text(
                model="",
                system=system,
                contents="\n".join(context_parts),
                temperature=0.7 if is_done else 0.9,
            )
            assistant_msg = response.text
            history.append({"role": "assistant", "content": assistant_msg})

            if is_done:
                return self._parse_plan(assistant_msg, project_slug, console)

            console.print()
            console.print(Markdown(assistant_msg))
            console.print()

    def _parse_plan(
        self,
        raw_json: str,
        project_slug: str,
        console: Console,
    ) -> CampaignPlan:
        """Parse LLM JSON output into a CampaignPlan and save it."""
        # Strip markdown fences if present
        text = raw_json.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

        data = json.loads(text)
        data["project_slug"] = project_slug

        plan = CampaignPlan(**data)

        # Validate workflow names
        registry = build_workflow_registry()
        for item in plan.calendar:
            if item.workflow not in registry._workflows:
                console.print(
                    f"[yellow]Warning: workflow '{item.workflow}' not found in registry[/yellow]"
                )

        path = self._manager.save_plan(plan)
        console.print(f"\n[bold green]Campaign saved to {path}[/bold green]")

        return plan
