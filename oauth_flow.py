"""OAuth2 Authorization Code flow helpers for schwab-mcp.

Thin Schwab-specific wrapper around ``tollbooth.oauth2_collector``.
Binds Schwab endpoint URLs, scope, and provider name. Only
``fetch_account_hash`` is Schwab-specific; everything else delegates
to the generic collector module.

server.py imports from this module with unchanged signatures.
"""

from __future__ import annotations

import logging

import httpx

from tollbooth.oauth2_collector import (
    begin_oauth_flow as _begin_oauth_flow,
    build_authorize_url as _build_authorize_url,
    decrypt_collector_code,
    exchange_code_for_token as _exchange_code_for_token,
    retrieve_code_from_collector,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Schwab-specific constants
# ---------------------------------------------------------------------------

_SCHWAB_AUTH_BASE = "https://api.schwabapi.com"
_SCHWAB_AUTHORIZE = f"{_SCHWAB_AUTH_BASE}/v1/oauth/authorize"
_SCHWAB_TOKEN = f"{_SCHWAB_AUTH_BASE}/v1/oauth/token"
_SCHWAB_SCOPE = "readonly"

__all__ = [
    "build_authorize_url",
    "begin_oauth_flow",
    "exchange_code_for_token",
    "fetch_account_hash",
    "decrypt_collector_code",
    "retrieve_code_from_collector",
]

# ---------------------------------------------------------------------------
# Schwab wrappers
# ---------------------------------------------------------------------------


def build_authorize_url(client_id: str, redirect_uri: str, state: str) -> str:
    """Construct the Schwab OAuth2 authorization URL."""
    return _build_authorize_url(
        _SCHWAB_AUTHORIZE, client_id, redirect_uri, state, scope=_SCHWAB_SCOPE
    )


def begin_oauth_flow(
    patron_npub: str,
    client_id: str,
    redirect_uri: str,
) -> dict:
    """Start a new Schwab OAuth flow. Returns the authorization URL."""
    return _begin_oauth_flow(
        patron_npub,
        client_id,
        redirect_uri,
        _SCHWAB_AUTHORIZE,
        scope=_SCHWAB_SCOPE,
        provider_name="Schwab",
    )


async def exchange_code_for_token(
    code: str,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
) -> dict:
    """Exchange an authorization code for a Schwab access/refresh token pair."""
    return await _exchange_code_for_token(
        code, client_id, client_secret, redirect_uri, _SCHWAB_TOKEN
    )


# ---------------------------------------------------------------------------
# Schwab-specific: account hash lookup (not in tollbooth)
# ---------------------------------------------------------------------------


async def fetch_account_hash(access_token: str) -> str:
    """GET /trader/v1/accounts/accountNumbers — returns the first hashValue."""
    async with httpx.AsyncClient() as http:
        resp = await http.get(
            f"{_SCHWAB_AUTH_BASE}/trader/v1/accounts/accountNumbers",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        resp.raise_for_status()
        accounts = resp.json()

    if not accounts:
        raise ValueError("No accounts found for this Schwab user.")

    return accounts[0]["hashValue"]
