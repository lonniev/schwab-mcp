"""Schwab OAuth2 token management.

Handles:
- Per-user client creation from operator creds + user token (multi-tenant)
- CLI bootstrap flow for initial token generation (single-tenant dev)
"""

import json
import logging
import os
import sys

import schwab.auth

from settings import Settings

logger = logging.getLogger(__name__)


def _read_token_from_env() -> dict:
    """Read token JSON from the SCHWAB_TOKEN_JSON environment variable."""
    raw = os.environ.get("SCHWAB_TOKEN_JSON", "")
    if not raw:
        raise EnvironmentError("SCHWAB_TOKEN_JSON is not set")
    return json.loads(raw)


def _write_token_noop(token: dict) -> None:
    """Token write callback for serverless -- logs a warning on refresh.

    In a serverless environment, we can't persist the refreshed token back
    to the environment variable. The operator must re-bootstrap periodically
    (Schwab refresh tokens expire after 7 days).
    """
    logger.warning(
        "Access token was refreshed at runtime. "
        "The SCHWAB_TOKEN_JSON env var is now stale. "
        "Re-run bootstrap within 7 days to avoid token expiration."
    )


def create_user_client(token_json: str) -> schwab.client.AsyncClient:
    """Create an authenticated async schwab-py client from operator env vars + user token.

    Used in multi-tenant mode: the operator supplies SCHWAB_CLIENT_ID and
    SCHWAB_CLIENT_SECRET via env vars; each user provides their own token_json
    via Secure Courier.

    Args:
        token_json: The user's Schwab OAuth token as a JSON string.

    Returns:
        An async schwab-py client ready for API calls.
    """
    settings = Settings()
    if not settings.schwab_client_id or not settings.schwab_client_secret:
        raise EnvironmentError(
            "SCHWAB_CLIENT_ID and SCHWAB_CLIENT_SECRET must be set for multi-tenant mode."
        )

    token_dict = json.loads(token_json) if isinstance(token_json, str) else token_json

    def _read_token() -> dict:
        return token_dict

    return schwab.auth.client_from_access_functions(
        api_key=settings.schwab_client_id,
        app_secret=settings.schwab_client_secret,
        token_read_func=_read_token,
        token_write_func=_write_token_noop,
        asyncio=True,
    )


def bootstrap(
    client_id: str | None = None,
    client_secret: str | None = None,
    callback_url: str | None = None,
    token_path: str = "token.json",
) -> None:
    """Run the interactive OAuth bootstrap flow.

    Opens a browser for the user to log in to Schwab, captures the
    callback, and writes the token to a local file. The resulting token
    JSON can then be copied into the SCHWAB_TOKEN_JSON env var for
    server deployment.
    """
    settings = Settings()
    cid = client_id or settings.schwab_client_id
    secret = client_secret or settings.schwab_client_secret
    cb = callback_url or settings.schwab_callback_url

    if not cid or not secret:
        raise EnvironmentError(
            "SCHWAB_CLIENT_ID and SCHWAB_CLIENT_SECRET must be set for bootstrap."
        )

    schwab.auth.client_from_manual_flow(
        api_key=cid,
        app_secret=secret,
        callback_url=cb,
        token_path=token_path,
    )

    with open(token_path) as f:
        token_json = f.read()

    print("\n--- Token generated successfully ---")
    print(f"Token saved to: {token_path}")
    print("\nCopy the following value into your SCHWAB_TOKEN_JSON env var:")
    print(token_json)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "bootstrap":
        import argparse

        parser = argparse.ArgumentParser(description="Bootstrap Schwab OAuth token")
        parser.add_argument("command", choices=["bootstrap"])
        parser.add_argument("--client-id", default=None)
        parser.add_argument("--client-secret", default=None)
        parser.add_argument("--callback-url", default=None)
        parser.add_argument("--token-path", default="token.json")
        args = parser.parse_args()

        bootstrap(
            client_id=args.client_id,
            client_secret=args.client_secret,
            callback_url=args.callback_url,
            token_path=args.token_path,
        )
    else:
        print(
            "Usage: python auth.py bootstrap "
            "[--client-id ...] [--client-secret ...] "
            "[--callback-url ...] [--token-path ...]"
        )
        sys.exit(1)
