from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, date, datetime

from rich.console import Console

from marketmenow.core.campaign_manager import CampaignManager
from marketmenow.core.project_manager import ProjectManager
from marketmenow.core.workflow_registry import WorkflowRegistry, build_workflow_registry
from marketmenow.models.campaign_plan import CampaignPlan, ContentCalendarItem

logger = logging.getLogger(__name__)

_POLL_INTERVAL_S = 60


class CampaignDaemon:
    """Background process that executes campaign calendar items on schedule."""

    def __init__(
        self,
        plan: CampaignPlan,
        workflow_registry: WorkflowRegistry | None = None,
        campaign_manager: CampaignManager | None = None,
        project_manager: ProjectManager | None = None,
        poll_interval: float = _POLL_INTERVAL_S,
    ) -> None:
        self._plan = plan
        self._registry = workflow_registry or build_workflow_registry()
        self._pm = project_manager or ProjectManager()
        self._manager = campaign_manager or CampaignManager(self._pm)
        self._poll_interval = poll_interval
        self._stop_event = asyncio.Event()
        self._console = Console()

    async def run(self) -> None:
        """Main loop: poll calendar, execute due items, sleep."""
        logger.info("Campaign daemon started for '%s'", self._plan.name)
        self._console.print(
            f"[bold cyan]Daemon started[/bold cyan] for campaign [bold]{self._plan.name}[/bold]"
        )
        self._write_daemon_state("running")

        try:
            while not self._stop_event.is_set():
                # Reload plan to get latest statuses
                try:
                    self._plan = self._manager.load_plan(self._plan.project_slug, self._plan.name)
                except Exception:
                    logger.warning("Failed to reload plan, using cached version")

                due_items = self._find_due_items()

                for item in due_items:
                    if self._stop_event.is_set():
                        break
                    await self._execute_item(item)

                # Check repurpose chains
                await self._check_repurpose_chains()

                # Wait or stop
                import contextlib

                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(
                        self._stop_event.wait(),
                        timeout=self._poll_interval,
                    )

        finally:
            self._write_daemon_state("stopped")
            logger.info("Campaign daemon stopped for '%s'", self._plan.name)

    def _find_due_items(self) -> list[ContentCalendarItem]:
        """Find calendar items that are due (date <= today, status == pending)."""
        today = date.today()
        return [
            item for item in self._plan.calendar if item.status == "pending" and item.date <= today
        ]

    async def _execute_item(self, item: ContentCalendarItem) -> None:
        """Run the workflow for a single calendar item."""
        self._console.print(
            f"  [bold cyan]>[/bold cyan] Executing {item.id}: "
            f"{item.workflow} on {item.platform} — {item.topic}"
        )

        workflow = self._registry.get(item.workflow)
        if workflow is None:
            logger.error("Workflow '%s' not found for item '%s'", item.workflow, item.id)
            self._manager.update_item_status(
                self._plan.project_slug, self._plan.name, item.id, "failed"
            )
            return

        project = self._pm.load_project(self._plan.project_slug)
        persona = None
        if project.default_persona:
            import contextlib

            with contextlib.suppress(Exception):
                persona = self._pm.load_persona(self._plan.project_slug, project.default_persona)

        params: dict[str, str | int | float | bool] = {
            "topic": item.topic,
            "brief": item.brief,
        }
        if item.cta:
            params["cta"] = item.cta

        try:
            result = await workflow.run(
                params,
                console=self._console,
                project=project,
                persona=persona,
            )
            if result.success:
                # Try to get capsule_id from the result
                capsule_id = ""
                for outcome in result.outcomes:
                    if hasattr(outcome, "capsule_id"):
                        capsule_id = str(outcome.capsule_id)

                self._manager.update_item_status(
                    self._plan.project_slug,
                    self._plan.name,
                    item.id,
                    "published",
                    capsule_id=capsule_id,
                )
                self._console.print(f"  [green]Completed: {item.id}[/green]")
            else:
                error_msg = "; ".join(o.error for o in result.outcomes if o.error)
                logger.error("Item '%s' failed: %s", item.id, error_msg)
                self._manager.update_item_status(
                    self._plan.project_slug, self._plan.name, item.id, "failed"
                )
        except Exception:
            logger.exception("Item '%s' raised exception", item.id)
            self._manager.update_item_status(
                self._plan.project_slug, self._plan.name, item.id, "failed"
            )

    async def _check_repurpose_chains(self) -> None:
        """If a source item is published, execute its target repurpose items."""
        published_ids = {item.id for item in self._plan.calendar if item.status == "published"}

        for chain in self._plan.repurpose_chains:
            if chain.source_item_id in published_ids:
                for target_id in chain.target_items:
                    target = next(
                        (i for i in self._plan.calendar if i.id == target_id),
                        None,
                    )
                    if target and target.status == "pending":
                        await self._execute_item(target)

    def generate_status_report(self) -> str:
        """Generate a summary of campaign progress."""
        total = len(self._plan.calendar)
        published = sum(1 for i in self._plan.calendar if i.status == "published")
        failed = sum(1 for i in self._plan.calendar if i.status == "failed")
        pending = sum(1 for i in self._plan.calendar if i.status == "pending")

        platforms = set(i.platform for i in self._plan.calendar if i.status == "published")

        lines = [
            f"Campaign: {self._plan.name}",
            f"Progress: {published}/{total} published, {failed} failed, {pending} pending",
            f"Platforms posted to: {', '.join(sorted(platforms)) or 'none yet'}",
        ]
        return "\n".join(lines)

    def stop(self) -> None:
        """Signal the daemon to stop gracefully."""
        self._stop_event.set()

    def _write_daemon_state(self, status: str) -> None:
        """Write daemon state to .daemon.json for status/stop commands."""
        daemon_dir = self._manager._campaign_dir(self._plan.project_slug, self._plan.name)
        state_file = daemon_dir / ".daemon.json"
        state = {
            "status": status,
            "pid": __import__("os").getpid(),
            "started_at": datetime.now(UTC).isoformat(),
            "campaign": self._plan.name,
        }
        state_file.write_text(json.dumps(state, indent=2), encoding="utf-8")
