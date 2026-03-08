"""Schwab OAuth2 token management.

Schwab API credentials (client_id, client_secret) are delivered by the
operator via Secure Courier (service="schwab-operator"). Per-user tokens
(token_json, account_hash) arrive via service="schwab". No env vars are
needed for Schwab OAuth app credentials.

Client creation is handled directly in server.py via vault._create_client().
"""

import sys

if __name__ == "__main__":
    print(
        "schwab-py bootstrap has been removed.\n"
        "Generate your OAuth token manually via Schwab's developer portal:\n"
        "  https://developer.schwab.com\n\n"
        "Then deliver your credentials via Secure Courier."
    )
    sys.exit(1)
