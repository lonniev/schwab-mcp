"""Thin async httpx client for the Schwab Trader API.

Replaces schwab-py with direct HTTP calls, giving full control over
endpoints, headers, and error handling. Bearer auth with proactive
token refresh (300s leeway).
"""

from __future__ import annotations

import asyncio
import base64
import logging
import time

import httpx

logger = logging.getLogger(__name__)

_DEFAULT_API_BASE = "https://api.schwabapi.com"
_REFRESH_LEEWAY_SECONDS = 300


class SchwabClient:
    """Async Schwab API client with bearer auth and token refresh."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        token_dict: dict,
        api_base: str = _DEFAULT_API_BASE,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._token = dict(token_dict)  # shallow copy so mutations are local
        self._api_base = api_base.rstrip("/")
        self._http = httpx.AsyncClient()
        self._refresh_lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Token management
    # ------------------------------------------------------------------

    async def _ensure_token(self) -> None:
        """Refresh the access token if it expires within the leeway window."""
        expires_at = self._token.get("expires_at", 0)
        if time.time() < expires_at - _REFRESH_LEEWAY_SECONDS:
            return

        async with self._refresh_lock:
            # Re-check after acquiring lock (another coroutine may have refreshed)
            if time.time() < self._token.get("expires_at", 0) - _REFRESH_LEEWAY_SECONDS:
                return
            await self._refresh_token()

    async def _refresh_token(self) -> None:
        """POST to /v1/oauth/token with Basic auth to refresh the access token."""
        url = f"{self._api_base}/v1/oauth/token"
        credentials = base64.b64encode(
            f"{self._client_id}:{self._client_secret}".encode()
        ).decode()

        resp = await self._http.post(
            url,
            headers={
                "Authorization": f"Basic {credentials}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            content=f"grant_type=refresh_token&refresh_token={self._token['refresh_token']}",
        )
        resp.raise_for_status()
        data = resp.json()

        self._token["access_token"] = data["access_token"]
        self._token["expires_at"] = time.time() + data.get("expires_in", 1800)
        if "refresh_token" in data:
            self._token["refresh_token"] = data["refresh_token"]

        logger.info("Schwab access token refreshed successfully.")

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    async def _get(self, path: str, params: dict | None = None) -> dict:
        """GET with bearer auth + auto-refresh. Returns parsed JSON."""
        await self._ensure_token()
        resp = await self._http.get(
            self._api_base + path,
            params=params,
            headers={"Authorization": f"Bearer {self._token['access_token']}"},
        )
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Convenience methods — one per Schwab endpoint we use
    # ------------------------------------------------------------------

    async def get_account(self, account_hash: str, fields: str | None = None) -> dict:
        """GET /trader/v1/accounts/{account_hash}"""
        params = {}
        if fields:
            params["fields"] = fields
        return await self._get(f"/trader/v1/accounts/{account_hash}", params or None)

    async def get_quotes(self, symbols: list[str]) -> dict:
        """GET /marketdata/v1/quotes?symbols=SYM1,SYM2"""
        return await self._get("/marketdata/v1/quotes", {"symbols": ",".join(symbols)})

    async def get_price_history(self, symbol: str, **params) -> dict:
        """GET /marketdata/v1/pricehistory?symbol=SYM&..."""
        params["symbol"] = symbol
        return await self._get("/marketdata/v1/pricehistory", params)

    async def get_option_chain(self, symbol: str, **params) -> dict:
        """GET /marketdata/v1/chains?symbol=SYM&..."""
        params["symbol"] = symbol
        return await self._get("/marketdata/v1/chains", params)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def close(self) -> None:
        """Close the underlying httpx client."""
        await self._http.aclose()
