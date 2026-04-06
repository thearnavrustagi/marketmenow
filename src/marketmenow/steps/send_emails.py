from __future__ import annotations

from pathlib import Path

from marketmenow.core.workflow import WorkflowContext, WorkflowError


class SendEmailsStep:
    """Send templated emails via SMTP (batch or single recipient)."""

    @property
    def name(self) -> str:
        return "send-emails"

    @property
    def description(self) -> str:
        return "Send templated emails"

    async def execute(self, ctx: WorkflowContext) -> None:
        from adapters.email.sender import send_batch, send_single
        from adapters.email.settings import EmailSettings

        settings = EmailSettings()

        template_path = ctx.require_param("template")
        template = Path(str(template_path))
        if not template.exists():
            raise WorkflowError(f"Template file not found: {template}")

        dry_run = bool(ctx.get_param("dry_run", False))
        subject = str(ctx.get_param("subject", "") or "") or None

        paraphraser = None
        if ctx.get_param("paraphrase", False):
            import os

            from adapters.email.paraphraser import EmailParaphraser

            creds = settings.google_application_credentials
            if creds and creds.exists():
                os.environ.setdefault("GOOGLE_APPLICATION_CREDENTIALS", str(creds.resolve()))
            paraphraser = EmailParaphraser(
                vertex_project=settings.vertex_ai_project,
                vertex_location=settings.vertex_ai_location,
                top_examples_path=settings.top_examples_path,
                max_examples=settings.max_examples_in_prompt,
                epsilon=settings.epsilon,
            )

        to = str(ctx.get_param("to", "") or "")
        csv_file_param = ctx.get_param("csv_file")

        if to:
            var_params = str(ctx.get_param("vars", "") or "")
            template_vars: dict[str, str] = {}
            for item in var_params.split(","):
                if "=" in item:
                    k, v = item.split("=", 1)
                    template_vars[k.strip()] = v.strip()

            result = await send_single(
                settings,
                template,
                subject,
                to,
                template_vars=template_vars,
                paraphraser=paraphraser,
                dry_run=dry_run,
            )
            results = [result]
        elif csv_file_param:
            csv_file = Path(str(csv_file_param))
            range_str = str(ctx.require_param("range"))
            start, end = (int(x) for x in range_str.split("-"))

            with ctx.console.status("[bold blue]Sending emails..."):
                results = await send_batch(
                    settings,
                    csv_file,
                    template,
                    subject,
                    start,
                    end,
                    paraphraser=paraphraser,
                    dry_run=dry_run,
                )
        else:
            raise WorkflowError("Provide --to for single send or --csv-file for batch")

        succeeded = sum(1 for r in results if r.success)
        failed = len(results) - succeeded
        mode = "DRY RUN" if dry_run else "sent"
        ctx.console.print(f"[green]{succeeded} {mode}[/green], [red]{failed} failed[/red]")
        ctx.set_artifact("send_results", results)
