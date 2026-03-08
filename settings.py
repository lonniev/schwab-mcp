"""Schwab MCP server settings loaded from environment variables."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Schwab MCP server settings.

    Operator env vars (required):
        SCHWAB_CLIENT_ID / SCHWAB_CLIENT_SECRET — Schwab OAuth app creds
        TOLLBOOTH_NOSTR_OPERATOR_NSEC — Nostr signing key
        NEON_DATABASE_URL — Postgres for NeonVault

    BTCPay (required for credits):
        BTCPAY_HOST / BTCPAY_STORE_ID / BTCPAY_API_KEY
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Schwab OAuth app credentials (operator-provided)
    schwab_client_id: str | None = None
    schwab_client_secret: str | None = None

    # Server binding
    schwab_mcp_host: str = "0.0.0.0"
    schwab_mcp_port: int = 8000

    # BTCPay Server (for Lightning invoices)
    btcpay_host: str | None = None
    btcpay_store_id: str | None = None
    btcpay_api_key: str | None = None
    btcpay_tier_config: str | None = None
    btcpay_user_tiers: str | None = None

    # Credit seeding for new users (0 = disabled)
    seed_balance_sats: int = 0

    # DPYC registry cache TTL
    dpyc_registry_cache_ttl_seconds: int = 300

    # Credit expiration
    credit_ttl_seconds: int | None = 604800  # 7 days

    # Commerce vault backend
    neon_database_url: str | None = None  # Serverless Postgres

    # Secure Courier (Nostr DM credential exchange)
    tollbooth_nostr_operator_nsec: str | None = None
    tollbooth_nostr_relays: str | None = None  # Comma-separated relay URLs

    # OAuth bootstrap callback URL (CLI only)
    schwab_callback_url: str = "https://127.0.0.1:8182"
