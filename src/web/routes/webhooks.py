from __future__ import annotations

import logging

from fastapi import APIRouter, Query, Request, Response

router = APIRouter(tags=["webhooks"])

logger = logging.getLogger(__name__)


def _get_verify_token() -> str:
    from adapters.instagram.settings import InstagramSettings

    return InstagramSettings().instagram_webhook_verify_token


@router.get("/webhooks/instagram")
async def instagram_webhook_verify(
    hub_mode: str = Query(..., alias="hub.mode"),
    hub_verify_token: str = Query(..., alias="hub.verify_token"),
    hub_challenge: str = Query(..., alias="hub.challenge"),
) -> Response:
    """Meta webhook verification (hub challenge-response)."""
    expected = _get_verify_token()
    if hub_mode == "subscribe" and hub_verify_token == expected:
        logger.info("Instagram webhook verified")
        return Response(content=hub_challenge, media_type="text/plain")
    logger.warning("Instagram webhook verification failed (bad token)")
    return Response(content="Forbidden", status_code=403)


@router.post("/webhooks/instagram")
async def instagram_webhook_event(request: Request) -> dict[str, str]:
    """Receive Instagram webhook events (comments, mentions, etc.)."""
    payload = await request.json()
    logger.info("Instagram webhook event: %s", payload)
    return {"status": "ok"}
