from __future__ import annotations

import logging

import httpx

_IG_GRAPH_BASE = "https://graph.facebook.com/v21.0"

logger = logging.getLogger(__name__)


class TokenManager:
    """Exchange short-lived Instagram/Facebook tokens for long-lived ones
    and refresh them before they expire.

    Meta token lifecycle:
      1. Short-lived user token (~1 h) obtained via OAuth / Graph Explorer.
      2. Exchange for long-lived token (~60 days) using app credentials.
      3. Refresh the long-lived token before it expires (returns a new
         long-lived token, also ~60 days).
    """

    def __init__(self, app_id: str, app_secret: str) -> None:
        self._app_id = app_id
        self._app_secret = app_secret
        self._client = httpx.AsyncClient(base_url=_IG_GRAPH_BASE, timeout=30.0)

    async def exchange_for_long_lived(self, short_lived_token: str) -> str:
        """Exchange a short-lived token for a long-lived one (~60 days)."""
        resp = await self._client.get(
            "/oauth/access_token",
            params={
                "grant_type": "fb_exchange_token",
                "client_id": self._app_id,
                "client_secret": self._app_secret,
                "fb_exchange_token": short_lived_token,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        token = data["access_token"]
        expires_in = data.get("expires_in", "unknown")
        logger.info("Exchanged for long-lived token (expires_in=%s seconds)", expires_in)
        return str(token)

    async def refresh(self, long_lived_token: str) -> str:
        """Refresh an existing long-lived token (returns a new long-lived token)."""
        resp = await self._client.get(
            "/oauth/access_token",
            params={
                "grant_type": "fb_exchange_token",
                "client_id": self._app_id,
                "client_secret": self._app_secret,
                "fb_exchange_token": long_lived_token,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        token = data["access_token"]
        logger.info("Refreshed long-lived token")
        return str(token)

    async def debug_token(self, token: str) -> dict[str, object]:
        """Inspect a token via the Graph API debug_token endpoint."""
        app_token = f"{self._app_id}|{self._app_secret}"
        resp = await self._client.get(
            "/debug_token",
            params={"input_token": token, "access_token": app_token},
        )
        resp.raise_for_status()
        return resp.json().get("data", {})  # type: ignore[no-any-return]

    async def ensure_long_lived(self, token: str) -> str:
        """If the token is short-lived, exchange it; otherwise return as-is.

        Uses ``debug_token`` to inspect expiry. If the token expires within
        7 days it is refreshed; if it is short-lived it is exchanged.
        """
        try:
            info = await self.debug_token(token)
        except httpx.HTTPStatusError:
            logger.warning("Could not debug token; returning as-is")
            return token

        expires_at = info.get("expires_at", 0)
        if isinstance(expires_at, int) and expires_at == 0:
            logger.info("Token does not expire (page token) -- using as-is")
            return token

        import time

        remaining = int(expires_at) - int(time.time()) if isinstance(expires_at, int) else 0

        if remaining < 3600:
            logger.info("Token expires in < 1 h -- exchanging for long-lived token")
            return await self.exchange_for_long_lived(token)

        seven_days = 7 * 24 * 3600
        if 0 < remaining < seven_days:
            logger.info("Token expires in < 7 days -- refreshing")
            return await self.refresh(token)

        logger.info("Token is valid for %d days -- no action needed", remaining // 86400)
        return token
