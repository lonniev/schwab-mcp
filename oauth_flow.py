"""OAuth2 Authorization Code flow helpers for schwab-mcp.

Self-contained module — no imports from server.py. Builds authorization URLs,
exchanges codes for tokens, and retrieves encrypted codes from the external
OAuth2 collector. Uses the patron's npub as the OAuth state parameter —
no server-side pending-state storage needed.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import time
import urllib.parse

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SCHWAB_AUTH_BASE = "https://api.schwabapi.com"

# ---------------------------------------------------------------------------
# URL builder
# ---------------------------------------------------------------------------


def build_authorize_url(client_id: str, redirect_uri: str, state: str) -> str:
    """Construct the Schwab OAuth2 authorization URL."""
    params = urllib.parse.urlencode({
        "response_type": "code",
        "client_id": client_id,
        "scope": "readonly",
        "redirect_uri": redirect_uri,
        "state": state,
    })
    return f"{_SCHWAB_AUTH_BASE}/v1/oauth/authorize?{params}"


# ---------------------------------------------------------------------------
# Begin flow
# ---------------------------------------------------------------------------


def begin_oauth_flow(
    patron_npub: str,
    client_id: str,
    redirect_uri: str,
) -> dict:
    """Start a new OAuth flow. Returns the authorization URL.

    Uses the patron's npub as the OAuth state parameter — the collector
    encrypts the auth code with SHA-256(npub) and the MCP server decrypts
    it on retrieval.
    """
    url = build_authorize_url(client_id, redirect_uri, patron_npub)
    return {
        "status": "pending",
        "authorize_url": url,
        "message": (
            "Open this URL in your browser to authorize with Schwab. "
            "After authorizing, call check_oauth_status to confirm."
        ),
    }


# ---------------------------------------------------------------------------
# Token exchange + account hash fetch
# ---------------------------------------------------------------------------


async def exchange_code_for_token(
    code: str,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
) -> dict:
    """Exchange an authorization code for an access/refresh token pair.

    POST /v1/oauth/token with Basic Auth and grant_type=authorization_code.
    Adds a computed ``expires_at`` field to the returned token dict.
    """
    credentials = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()

    async with httpx.AsyncClient() as http:
        resp = await http.post(
            f"{_SCHWAB_AUTH_BASE}/v1/oauth/token",
            headers={
                "Authorization": f"Basic {credentials}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            content=urllib.parse.urlencode({
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
            }),
        )
        resp.raise_for_status()
        token = resp.json()

    token["expires_at"] = time.time() + token.get("expires_in", 1800)
    return token


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


# ---------------------------------------------------------------------------
# External collector retrieval + decryption
# ---------------------------------------------------------------------------


def _decrypt_code(encrypted_b64: str, state: str) -> str:
    """Decrypt an authorization code encrypted by the collector.

    XOR with SHA-256(state) keystream — symmetric with collector's _encrypt_code.
    """
    key = hashlib.sha256(state.encode()).digest()
    encrypted = base64.urlsafe_b64decode(encrypted_b64)
    decrypted = bytes(c ^ key[i % 32] for i, c in enumerate(encrypted))
    return decrypted.decode()


async def retrieve_code_from_collector(
    collector_url: str,
    state_token: str,
) -> str | None:
    """Fetch an authorization code from the external OAuth2 collector.

    The collector stores codes encrypted with SHA-256(state). This function
    retrieves the encrypted code and decrypts it.
    Returns the plaintext code string or None if not yet available.
    """
    url = f"{collector_url.rstrip('/')}/oauth/retrieve"
    async with httpx.AsyncClient() as http:
        resp = await http.get(url, params={"state": state_token})
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        encrypted_code = resp.json()["code"]
    return _decrypt_code(encrypted_code, state_token)
