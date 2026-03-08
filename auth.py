"""Schwab OAuth2 token management.

Handles:
- Per-user client creation from operator creds + user token (multi-tenant)
- CLI bootstrap note (manual token generation via Schwab's OAuth portal)
"""

import logging
import sys

from settings import Settings

logger = logging.getLogger(__name__)


def create_user_client(token_json: str):
    """Create an authenticated SchwabClient from operator env vars + user token.

    Used in multi-tenant mode: the operator supplies SCHWAB_CLIENT_ID and
    SCHWAB_CLIENT_SECRET via env vars; each user provides their own token_json
    via Secure Courier.

    Respects SCHWAB_TRADER_API if set to a non-default base URL.

    Args:
        token_json: The user's Schwab OAuth token as a JSON string.

    Returns:
        A SchwabClient ready for API calls.
    """
    from vault import _create_client

    settings = Settings()
    if not settings.schwab_client_id or not settings.schwab_client_secret:
        raise EnvironmentError(
            "SCHWAB_CLIENT_ID and SCHWAB_CLIENT_SECRET must be set for multi-tenant mode."
        )

    return _create_client(
        settings.schwab_client_id,
        settings.schwab_client_secret,
        token_json,
        api_base=settings.schwab_trader_api,
    )


if __name__ == "__main__":
    print(
        "schwab-py bootstrap has been removed.\n"
        "Generate your OAuth token manually via Schwab's developer portal:\n"
        "  https://developer.schwab.com\n\n"
        "Then set SCHWAB_TOKEN_JSON with the resulting JSON."
    )
    sys.exit(1)
