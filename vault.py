"""Multi-tenant session management for schwab-mcp.

Per-user Schwab OAuth sessions backed by in-memory cache.
Each user delivers their token_json + account_hash via Secure Courier;
the server creates an AsyncClient from operator creds + user token
and caches it here.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field

import schwab.auth
from schwab.client import AsyncClient

logger = logging.getLogger(__name__)

SESSION_TTL_SECONDS = 3600  # 1 hour


@dataclass
class UserSession:
    """Per-user session holding a cached Schwab AsyncClient."""

    token_json: str  # Schwab OAuth token blob (JSON string)
    account_hash: str  # Schwab account hash
    client: AsyncClient  # Cached async client
    npub: str | None = None
    created_at: float = field(default_factory=time.time)

    def __repr__(self) -> str:
        age = int(time.time() - self.created_at)
        return (
            f"UserSession(npub={self.npub!r}, age={age}s, "
            f"account_hash=<redacted>, token=<redacted>)"
        )

    @property
    def is_expired(self) -> bool:
        return (time.time() - self.created_at) > SESSION_TTL_SECONDS

    @property
    def age_seconds(self) -> int:
        return int(time.time() - self.created_at)


_sessions: dict[str, UserSession] = {}  # horizon_user_id -> session
_dpyc_sessions: dict[str, str] = {}  # horizon_user_id -> npub


def _create_client_from_token(
    client_id: str,
    client_secret: str,
    token_json: str,
) -> AsyncClient:
    """Create an async Schwab client from operator creds + user token JSON."""
    token_dict = json.loads(token_json) if isinstance(token_json, str) else token_json

    def _read_token() -> dict:
        return token_dict

    def _write_token_noop(token: dict) -> None:
        logger.warning(
            "Access token refreshed at runtime. "
            "User should re-deliver token via Secure Courier within 7 days."
        )

    return schwab.auth.client_from_access_functions(
        api_key=client_id,
        app_secret=client_secret,
        token_read_func=_read_token,
        token_write_func=_write_token_noop,
        asyncio=True,
    )


def set_session(
    user_id: str,
    token_json: str,
    account_hash: str,
    client: AsyncClient,
    npub: str | None = None,
) -> UserSession:
    """Create or replace a session for a user."""
    session = UserSession(
        token_json=token_json,
        account_hash=account_hash,
        client=client,
        npub=npub,
    )
    _sessions[user_id] = session
    if npub:
        _dpyc_sessions[user_id] = npub
    return session


def get_session(user_id: str) -> UserSession | None:
    """Get active session, returning None if expired or absent."""
    session = _sessions.get(user_id)
    if session and session.is_expired:
        del _sessions[user_id]
        return None
    return session


async def clear_session(user_id: str) -> None:
    """Remove a session and close its async client."""
    session = _sessions.pop(user_id, None)
    _dpyc_sessions.pop(user_id, None)
    if session and session.client:
        try:
            await session.client.close_async_session()
        except Exception:
            pass


def get_dpyc_npub(user_id: str) -> str | None:
    """Get the DPYC npub for a Horizon user, if activated."""
    return _dpyc_sessions.get(user_id)
