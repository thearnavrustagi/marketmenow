"""Shared tweet article parsing utilities for discovery vectors."""

from __future__ import annotations

import logging

from marketmenow.outreach.models import DiscoveredProspectPost

logger = logging.getLogger(__name__)


async def parse_tweet_article(
    article: object,
    source_vector: str,
) -> DiscoveredProspectPost | None:
    """Extract a DiscoveredProspectPost from a tweet article DOM element.

    Mirrors the parsing logic from adapters.twitter.discovery._parse_tweet_article
    but returns the outreach model type with source_vector tagging.
    """
    try:
        text_el = article.locator('div[data-testid="tweetText"]')  # type: ignore[attr-defined]
        post_text = await text_el.inner_text(timeout=3_000)
    except Exception:
        post_text = ""

    if not post_text.strip():
        return None

    try:
        time_el = article.locator("time").first  # type: ignore[attr-defined]
        link_el = time_el.locator("xpath=ancestor::a")
        href = await link_el.get_attribute("href", timeout=3_000)
        post_url = f"https://x.com{href}" if href and not href.startswith("http") else (href or "")
    except Exception:
        return None

    if not post_url:
        return None

    engagement = 0
    for testid in ("like", "retweet", "reply"):
        try:
            metric_el = article.locator(  # type: ignore[attr-defined]
                f'button[data-testid="{testid}"] span span'
            )
            metric_text = await metric_el.inner_text(timeout=1_000)
            engagement += _parse_metric(metric_text)
        except Exception:
            pass

    try:
        handle_el = article.locator(  # type: ignore[attr-defined]
            'div[data-testid="User-Name"] a[role="link"][tabindex="-1"]'
        )
        handle_href = await handle_el.get_attribute("href", timeout=2_000)
        author = handle_href.strip("/").split("/")[-1] if handle_href else ""
    except Exception:
        author = ""

    if not author:
        return None

    return DiscoveredProspectPost(
        author_handle=author,
        post_url=post_url,
        post_text=post_text[:1000],
        engagement_score=engagement,
        source_vector=source_vector,
    )


def _parse_metric(text: str) -> int:
    text = text.strip().replace(",", "")
    if not text:
        return 0
    multiplier = 1
    if text.endswith("K"):
        multiplier = 1_000
        text = text[:-1]
    elif text.endswith("M"):
        multiplier = 1_000_000
        text = text[:-1]
    try:
        return int(float(text) * multiplier)
    except ValueError:
        return 0
