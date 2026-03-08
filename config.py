"""Environment configuration for Schwab MCP server."""

import os


def get_schwab_client_id() -> str:
    val = os.environ.get("SCHWAB_CLIENT_ID", "")
    if not val:
        raise EnvironmentError("SCHWAB_CLIENT_ID is not set")
    return val


def get_schwab_client_secret() -> str:
    val = os.environ.get("SCHWAB_CLIENT_SECRET", "")
    if not val:
        raise EnvironmentError("SCHWAB_CLIENT_SECRET is not set")
    return val


def get_schwab_token_json() -> str:
    val = os.environ.get("SCHWAB_TOKEN_JSON", "")
    if not val:
        raise EnvironmentError("SCHWAB_TOKEN_JSON is not set")
    return val


def get_schwab_account_hash() -> str:
    val = os.environ.get("SCHWAB_ACCOUNT_HASH", "")
    if not val:
        raise EnvironmentError("SCHWAB_ACCOUNT_HASH is not set")
    return val


CALLBACK_URL = "https://127.0.0.1:8182"


def get_mcp_host() -> str:
    return os.environ.get("SCHWAB_MCP_HOST", "127.0.0.1")


def get_mcp_port() -> int:
    return int(os.environ.get("SCHWAB_MCP_PORT", "8000"))
