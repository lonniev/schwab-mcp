"""Schwab MCP server settings loaded from environment variables."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Schwab MCP server settings.

    Operator env vars (required):
        TOLLBOOTH_NOSTR_OPERATOR_NSEC — Nostr signing key
        NEON_DATABASE_URL — Postgres for NeonVault

    Schwab API credentials (client_id / client_secret) are delivered
    via Secure Courier (service="schwab-operator"), NOT env vars.

    BTCPay (required for credits):
        BTCPAY_HOST / BTCPAY_STORE_ID / BTCPAY_API_KEY
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Schwab Trader API base URL (no trailing slash)
    schwab_trader_api: str = "https://api.schwabapi.com"

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

