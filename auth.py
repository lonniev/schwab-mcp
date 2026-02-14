"""Schwab OAuth2 token management.

Handles loading tokens from environment variables for server runtime
and provides a CLI bootstrap flow for initial token generation.
"""

import json
import os
import sys

import schwab.auth

from config import CALLBACK_URL, get_schwab_client_id, get_schwab_client_secret


def _read_token_from_env() -> dict:
    """Read token JSON from the SCHWAB_TOKEN_JSON environment variable."""
    raw = os.environ.get("SCHWAB_TOKEN_JSON", "")
    if not raw:
        raise EnvironmentError("SCHWAB_TOKEN_JSON is not set")
    return json.loads(raw)


def _write_token_noop(token: dict) -> None:
    """Token write callback for serverless — logs a warning on refresh.

    In a serverless environment, we can't persist the refreshed token back
    to the environment variable. The operator must re-bootstrap periodically
    (Schwab refresh tokens expire after 7 days).
    """
    import logging

    logging.getLogger(__name__).warning(
        "Access token was refreshed at runtime. "
        "The SCHWAB_TOKEN_JSON env var is now stale. "
        "Re-run bootstrap within 7 days to avoid token expiration."
    )


def create_client() -> schwab.auth.Client:
    """Create an authenticated schwab-py client from environment variables.

    Uses client_from_access_functions so we can load the token from an
    env var rather than a file path.
    """
    return schwab.auth.client_from_access_functions(
        api_key=get_schwab_client_id(),
        app_secret=get_schwab_client_secret(),
        token_read_func=_read_token_from_env,
        token_write_func=_write_token_noop,
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
    cid = client_id or get_schwab_client_id()
    secret = client_secret or get_schwab_client_secret()
    cb = callback_url or CALLBACK_URL

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
