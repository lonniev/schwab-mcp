"""OAuth2 Authorization Code flow helpers for schwab-mcp.

Self-contained module — no imports from server.py. Manages pending
OAuth state, HMAC-signed state tokens, Schwab token exchange, and
account-hash lookup.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import time
import urllib.parse
from dataclasses import dataclass, field

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SCHWAB_AUTH_BASE = "https://api.schwabapi.com"
_STATE_TTL_SECONDS = 600  # 10 minutes

# ---------------------------------------------------------------------------
# Pending-state store
# ---------------------------------------------------------------------------


@dataclass
class OAuthPendingState:
    """In-memory record tracking a pending OAuth authorization."""

    patron_npub: str
    horizon_user_id: str
    created_at: float = field(default_factory=time.time)
    completed: bool = False
    result: dict | None = None
    error: str | None = None


_pending_states: dict[str, OAuthPendingState] = {}  # state_token -> pending


def _cleanup_expired() -> None:
    """Remove expired pending states (older than TTL)."""
    now = time.time()
    expired = [k for k, v in _pending_states.items() if now - v.created_at > _STATE_TTL_SECONDS]
    for k in expired:
        del _pending_states[k]


# ---------------------------------------------------------------------------
# HMAC-signed state tokens
# ---------------------------------------------------------------------------


def generate_state_token(signing_key: bytes) -> str:
    """Create an HMAC-signed state token: ``random_hex.signature_hex``."""
    nonce = os.urandom(16).hex()
    sig = hmac.new(signing_key, nonce.encode(), hashlib.sha256).hexdigest()
    return f"{nonce}.{sig}"


def validate_state_token(token: str, signing_key: bytes) -> bool:
    """Verify the HMAC signature on a state token."""
    if "." not in token:
        return False
    nonce, sig = token.split(".", 1)
    expected = hmac.new(signing_key, nonce.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(sig, expected)


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
# Begin / check flow
# ---------------------------------------------------------------------------


def begin_oauth_flow(
    horizon_user_id: str,
    patron_npub: str,
    client_id: str,
    redirect_uri: str,
    signing_key: bytes,
) -> dict:
    """Start a new OAuth flow. Returns the authorization URL and state token.

    If an existing non-expired flow exists for this user, reuses it.
    """
    _cleanup_expired()

    # Reuse existing pending flow for this user
    for token, pending in _pending_states.items():
        if pending.horizon_user_id == horizon_user_id and not pending.completed:
            url = build_authorize_url(client_id, redirect_uri, token)
            return {
                "status": "pending",
                "authorize_url": url,
                "message": (
                    "Open this URL in your browser to authorize with Schwab. "
                    "After authorizing, call check_oauth_status to confirm."
                ),
            }

    state_token = generate_state_token(signing_key)
    _pending_states[state_token] = OAuthPendingState(
        patron_npub=patron_npub,
        horizon_user_id=horizon_user_id,
    )

    url = build_authorize_url(client_id, redirect_uri, state_token)
    return {
        "status": "pending",
        "authorize_url": url,
        "message": (
            "Open this URL in your browser to authorize with Schwab. "
            "After authorizing, call check_oauth_status to confirm."
        ),
    }


def check_oauth_status_for_user(horizon_user_id: str) -> dict:
    """Check whether the OAuth flow has completed for a given user."""
    _cleanup_expired()

    for pending in _pending_states.values():
        if pending.horizon_user_id != horizon_user_id:
            continue
        if pending.completed:
            if pending.error:
                return {"status": "failed", "error": pending.error}
            return {"status": "completed", "message": "Session activated successfully."}
        return {
            "status": "pending",
            "message": "Waiting for browser authorization. Open the URL from begin_oauth.",
        }

    return {"status": "no_flow", "message": "No OAuth flow in progress. Call begin_oauth first."}


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
    import base64

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
# Callback handler
# ---------------------------------------------------------------------------


async def handle_oauth_callback(
    code: str,
    state: str,
    signing_key: bytes,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
) -> OAuthPendingState:
    """Validate state, exchange code, fetch account hash, mark complete.

    Returns the pending state object (with result or error populated).
    Raises ValueError for invalid/expired state tokens.
    """
    if not validate_state_token(state, signing_key):
        raise ValueError("Invalid state token — possible CSRF or tampering.")

    _cleanup_expired()

    pending = _pending_states.get(state)
    if pending is None:
        raise ValueError("State token expired or not found. Please start a new OAuth flow.")

    try:
        token = await exchange_code_for_token(code, client_id, client_secret, redirect_uri)
        account_hash = await fetch_account_hash(token["access_token"])

        pending.completed = True
        pending.result = {
            "token": token,
            "account_hash": account_hash,
        }
    except Exception as exc:
        pending.completed = True
        pending.error = str(exc)

    return pending


# ---------------------------------------------------------------------------
# HTML response templates
# ---------------------------------------------------------------------------

_BODY_STYLE = (
    "font-family:system-ui,sans-serif;"
    "max-width:480px;margin:80px auto;text-align:center"
)

SUCCESS_HTML = (
    "<!DOCTYPE html><html><head><title>Schwab MCP — Authorized</title></head>"
    f'<body style="{_BODY_STYLE}">'
    "<h1>Authorization Successful</h1>"
    "<p>Your Schwab session has been activated. "
    "You can close this tab and return to your MCP client.</p>"
    "<p>Call <code>check_oauth_status</code> to confirm.</p>"
    "</body></html>"
)

ERROR_HTML_TEMPLATE = (
    "<!DOCTYPE html><html><head><title>Schwab MCP — Error</title></head>"
    f'<body style="{_BODY_STYLE}">'
    "<h1>Authorization Failed</h1>"
    "<p>{error}</p>"
    "<p>Please return to your MCP client and try again "
    "with <code>begin_oauth</code>.</p>"
    "</body></html>"
)
