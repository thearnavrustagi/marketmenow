from __future__ import annotations

import asyncio
import contextlib
import csv
import logging
import re
from collections.abc import Callable
from email.message import EmailMessage
from pathlib import Path

import aiosmtplib
import yaml
from jinja2 import BaseLoader, Environment

from .models import ContactRow, SendResult
from .paraphraser import EmailParaphraser
from .settings import EmailSettings

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[int, int, str, bool, str], None]
"""(current_index, total, email, success, error) -- called after each send attempt."""

_FRONT_MATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def parse_template(raw: str) -> tuple[dict[str, str], str]:
    """Split optional YAML front-matter from the HTML body.

    Returns ``(metadata_dict, html_body)``.  If no front-matter is
    present the metadata dict is empty.
    """
    m = _FRONT_MATTER_RE.match(raw)
    if not m:
        return {}, raw
    meta: dict[str, str] = yaml.safe_load(m.group(1)) or {}
    html = raw[m.end() :]
    return meta, html


def read_contacts(
    csv_path: Path,
    start: int,
    end: int,
) -> list[tuple[int, ContactRow]]:
    """Read rows ``[start, end)`` from *csv_path* (0-indexed data rows, header excluded)."""
    contacts: list[tuple[int, ContactRow]] = []
    with csv_path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row_idx, row in enumerate(reader):
            if row_idx < start:
                continue
            if row_idx >= end:
                break
            email = row.get("email", "").strip()
            if not email:
                logger.warning("Row %d has no email — skipping", row_idx)
                continue
            fields = {k: v for k, v in row.items() if k != "email"}
            contacts.append((row_idx, ContactRow(email=email, fields=fields)))
    return contacts


def render_email(
    template_html: str,
    subject_template: str,
    variables: dict[str, str],
) -> tuple[str, str]:
    """Return ``(rendered_subject, rendered_html)``."""
    env = Environment(loader=BaseLoader(), autoescape=False)
    html = env.from_string(template_html).render(variables)
    subject = env.from_string(subject_template).render(variables)
    return subject, html


def _build_message(
    *,
    sender: str,
    to: str,
    subject: str,
    html_body: str,
    bcc: str,
) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = to
    msg["Subject"] = subject
    msg["Bcc"] = bcc
    msg.set_content(html_body, subtype="html")
    return msg


async def send_single(
    settings: EmailSettings,
    template_path: Path,
    subject_template: str | None,
    to_address: str,
    *,
    template_vars: dict[str, str] | None = None,
    paraphraser: EmailParaphraser | None = None,
    dry_run: bool = False,
) -> SendResult:
    """Send one email to *to_address*.  Handy for quick tests."""
    raw = template_path.read_text(encoding="utf-8")
    meta, template_html = parse_template(raw)

    if subject_template is None:
        subject_template = meta.get("subject")
    if not subject_template:
        raise ValueError(
            "No subject provided. Pass -s on the CLI or add a "
            "'subject' field in the template's YAML front-matter."
        )

    if paraphraser is not None:
        template_html = await paraphraser.paraphrase(template_html)

    variables = {"email": to_address, **(template_vars or {})}
    subject, html = render_email(template_html, subject_template, variables)
    sender = settings.sender_display

    if dry_run:
        logger.info("[DRY RUN] → %s | Subject: %s", to_address, subject)
        return SendResult(
            row_index=0,
            email=to_address,
            success=True,
            rendered_html=html,
            rendered_subject=subject,
        )

    async with aiosmtplib.SMTP(
        hostname=settings.smtp_host,
        port=settings.smtp_port,
        use_tls=settings.smtp_use_ssl,
        start_tls=settings.smtp_use_tls,
    ) as smtp:
        await smtp.login(settings.smtp_username, settings.smtp_password)
        msg = _build_message(
            sender=sender,
            to=to_address,
            subject=subject,
            html_body=html,
            bcc=sender,
        )
        await smtp.send_message(msg)

    logger.info("→ %s  ✓", to_address)
    return SendResult(row_index=0, email=to_address, success=True)


async def send_batch(
    settings: EmailSettings,
    csv_path: Path,
    template_path: Path,
    subject_template: str | None,
    start: int,
    end: int,
    *,
    paraphraser: EmailParaphraser | None = None,
    dry_run: bool = False,
    on_progress: ProgressCallback | None = None,
) -> list[SendResult]:
    """Send emails to rows ``[start, end)`` of the CSV."""
    raw = template_path.read_text(encoding="utf-8")
    meta, base_html = parse_template(raw)

    if subject_template is None:
        subject_template = meta.get("subject")
    if not subject_template:
        raise ValueError(
            "No subject provided. Pass -s on the CLI or add a "
            "'subject' field in the template's YAML front-matter."
        )

    contacts = read_contacts(csv_path, start, end)
    total = len(contacts)

    if total == 0:
        logger.info("No contacts in range [%d, %d)", start, end)
        return []

    if paraphraser is not None:
        html_variants = await paraphraser.paraphrase_many(base_html, total)
    else:
        html_variants = [base_html] * total

    results: list[SendResult] = []
    sender = settings.sender_display

    if dry_run:
        for i, ((row_idx, contact), template_html) in enumerate(
            zip(contacts, html_variants, strict=True),
            1,
        ):
            subject, html = render_email(
                template_html,
                subject_template,
                contact.template_vars,
            )
            result = SendResult(
                row_index=row_idx,
                email=contact.email,
                success=True,
                rendered_html=html,
                rendered_subject=subject,
            )
            results.append(result)
            if on_progress:
                on_progress(i, total, contact.email, True, "")
            logger.info(
                "[DRY RUN] Row %d → %s | Subject: %s",
                row_idx,
                contact.email,
                subject,
            )
        return results

    delay = settings.smtp_send_delay
    reconnect_every = settings.smtp_reconnect_every

    async def _connect() -> aiosmtplib.SMTP:
        smtp = aiosmtplib.SMTP(
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            use_tls=settings.smtp_use_ssl,
            start_tls=settings.smtp_use_tls,
        )
        await smtp.connect()
        await smtp.login(settings.smtp_username, settings.smtp_password)
        return smtp

    smtp = await _connect()
    try:
        for i, ((row_idx, contact), template_html) in enumerate(
            zip(contacts, html_variants, strict=True),
            1,
        ):
            if reconnect_every > 0 and i > 1 and (i - 1) % reconnect_every == 0:
                with contextlib.suppress(Exception):
                    await smtp.quit()
                smtp = await _connect()
                logger.info("Reconnected SMTP after %d emails", i - 1)

            subject, html = render_email(
                template_html,
                subject_template,
                contact.template_vars,
            )
            msg = _build_message(
                sender=sender,
                to=contact.email,
                subject=subject,
                html_body=html,
                bcc=sender,
            )

            result: SendResult | None = None
            for attempt in range(3):
                try:
                    await smtp.send_message(msg)
                    result = SendResult(row_index=row_idx, email=contact.email, success=True)
                    logger.info("Row %d → %s  ✓", row_idx, contact.email)
                    break
                except Exception as exc:
                    if "421" in str(exc) and attempt < 2:
                        logger.warning(
                            "Row %d → %s  421 rate limit, reconnecting in 5s…",
                            row_idx,
                            contact.email,
                        )
                        await asyncio.sleep(5)
                        with contextlib.suppress(Exception):
                            await smtp.quit()
                        smtp = await _connect()
                    else:
                        result = SendResult(
                            row_index=row_idx,
                            email=contact.email,
                            success=False,
                            error=str(exc),
                        )
                        logger.error("Row %d → %s  ✗ %s", row_idx, contact.email, exc)
                        break
            if result is None:
                result = SendResult(
                    row_index=row_idx, email=contact.email, success=False, error="max retries"
                )

            results.append(result)
            if on_progress:
                on_progress(i, total, contact.email, result.success, result.error)

            if delay > 0 and i < total:
                await asyncio.sleep(delay)
    finally:
        with contextlib.suppress(Exception):
            await smtp.quit()

    return results
