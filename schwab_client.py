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
        on_token_refresh=None,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._token = dict(token_dict)  # shallow copy so mutations are local
        self._api_base = api_base.rstrip("/")
        self._http = httpx.AsyncClient()
        self._refresh_lock = asyncio.Lock()
        # Optional async callback fired after a successful refresh.
        # Wired by schwab-mcp to persist rotated tokens to the vault.
        self._on_token_refresh = on_token_refresh

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

        # Persist the rotated token to vault if a callback is wired.
        # Without this, a refresh-token rotation here would be lost
        # on the next process restart, forcing the user back through
        # the browser OAuth dance.
        if self._on_token_refresh is not None:
            try:
                await self._on_token_refresh(self._token)
            except Exception as exc:
                logger.warning("on_token_refresh callback failed: %s", exc)

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

    async def get_movers(self, index: str, **params) -> dict:
        """GET /marketdata/v1/movers/{index}"""
        return await self._get(f"/marketdata/v1/movers/{index}", params or None)

    async def get_market_hours(self, markets: str, date: str | None = None) -> dict:
        """GET /marketdata/v1/markets?markets=equity,option&date=..."""
        params: dict[str, str] = {"markets": markets}
        if date:
            params["date"] = date
        return await self._get("/marketdata/v1/markets", params)

    async def search_instruments(self, symbol: str, projection: str = "symbol-search") -> dict:
        """GET /marketdata/v1/instruments?symbol=...&projection=..."""
        return await self._get(
            "/marketdata/v1/instruments",
            {"symbol": symbol, "projection": projection},
        )

    async def get_option_chain(self, symbol: str, **params) -> dict:
        """GET /marketdata/v1/chains?symbol=SYM&..."""
        params["symbol"] = symbol
        return await self._get("/marketdata/v1/chains", params)

    async def get_orders(
        self,
        account_hash: str,
        from_entered_time: str,
        to_entered_time: str,
        status: str | None = None,
        max_results: int = 3000,
    ) -> list[dict]:
        """GET /trader/v1/accounts/{account_hash}/orders"""
        params: dict[str, str | int] = {
            "fromEnteredTime": from_entered_time,
            "toEnteredTime": to_entered_time,
            "maxResults": max_results,
        }
        if status:
            params["status"] = status
        return await self._get(f"/trader/v1/accounts/{account_hash}/orders", params)

    async def get_order(self, account_hash: str, order_id: str) -> dict:
        """GET /trader/v1/accounts/{account_hash}/orders/{orderId}"""
        return await self._get(f"/trader/v1/accounts/{account_hash}/orders/{order_id}")

    async def get_transactions(
        self,
        account_hash: str,
        start_date: str,
        end_date: str,
        transaction_types: str | None = None,
    ) -> list[dict]:
        """GET /trader/v1/accounts/{account_hash}/transactions"""
        params: dict[str, str] = {
            "startDate": start_date,
            "endDate": end_date,
        }
        if transaction_types:
            params["types"] = transaction_types
        return await self._get(
            f"/trader/v1/accounts/{account_hash}/transactions", params
        )

    async def get_transaction(self, account_hash: str, transaction_id: str) -> dict:
        """GET /trader/v1/accounts/{account_hash}/transactions/{transactionId}"""
        return await self._get(
            f"/trader/v1/accounts/{account_hash}/transactions/{transaction_id}"
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def close(self) -> None:
        """Close the underlying httpx client."""
        await self._http.aclose()
