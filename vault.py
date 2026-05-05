"""Per-call Schwab session construction for schwab-mcp.

A ``UserSession`` is a transient bundle of (token, account_hash,
SchwabClient) built fresh from the vault on each paid call.  No
in-memory cache: ``runtime.restore_oauth_session`` handles refresh
and persistence on every call, so a rotated refresh_token always
reaches the vault and survives process restart.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from schwab_client import SchwabClient

logger = logging.getLogger(__name__)

_DEFAULT_API_BASE = "https://api.schwabapi.com"


@dataclass
class UserSession:
    """Bundle of patron credentials + a live SchwabClient for one call."""

    token_json: str  # Schwab OAuth token blob (JSON string)
    account_hash: str  # Schwab account hash
    client: SchwabClient  # Live async client
    npub: str | None = None

    def __repr__(self) -> str:
        return (
            f"UserSession(npub={self.npub!r}, "
            f"account_hash=<redacted>, token=<redacted>)"
        )


def _create_client(
    client_id: str,
    client_secret: str,
    token_json: str,
    api_base: str = _DEFAULT_API_BASE,
    on_token_refresh=None,
) -> SchwabClient:
    """Create a SchwabClient from operator creds + user token JSON.

    ``on_token_refresh`` is an optional ``async (token_dict) -> None``
    callback the SchwabClient invokes after a successful in-memory
    token refresh.  schwab-mcp wires it to persist the rotated token
    back to the vault so a new refresh_token survives process
    restart.
    """
    token_dict = json.loads(token_json) if isinstance(token_json, str) else token_json
    return SchwabClient(
        client_id, client_secret, token_dict, api_base,
        on_token_refresh=on_token_refresh,
    )
