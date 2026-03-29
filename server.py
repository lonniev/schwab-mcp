"""Schwab MCP Server — multi-tenant brokerage data for Claude.ai.

Tollbooth-monetized, DPYC-native. Standard DPYC tools (check_balance,
purchase_credits, Secure Courier, Oracle, pricing) are provided by
``register_standard_tools`` from the tollbooth-dpyc wheel. Only
domain-specific Schwab brokerage tools are defined here.
"""

from __future__ import annotations

import logging
from typing import Any

from fastmcp import FastMCP
from tollbooth.constants import ToolTier
from tollbooth.credential_templates import CredentialTemplate, FieldSpec
from tollbooth.runtime import OperatorRuntime, register_standard_tools
from tollbooth.slug_tools import make_slug_tool

logger = logging.getLogger(__name__)

mcp = FastMCP(
    "Schwab MCP",
    instructions=(
        "Schwab MCP — AI agent access to Charles Schwab brokerage data, "
        "monetized via DPYC Tollbooth Lightning micropayments.\n\n"
        "## Getting Started\n\n"
        "1. Call `session_status` to check your current session.\n"
        "2. **Operator setup** (one-time): The operator delivers Schwab API app "
        "credentials via Secure Courier with `service='schwab-operator'`:\n"
        '   - Call `request_credential_channel(service="schwab-operator", '
        "recipient_npub=<operator_npub>)`\n"
        '   - Reply with JSON: `{"app_key": "...", "secret": "..."}`\n'
        "   - Call `receive_credentials(sender_npub=<operator_npub>, "
        'service="schwab-operator")`\n\n'
        "3. **Patron onboarding** (per-user) — choose one:\n\n"
        "   **Option A — OAuth (recommended):**\n"
        "   - Call `begin_oauth(patron_npub=<your_npub>)` to get an authorization URL\n"
        "   - Open the URL in your browser and log in to Schwab\n"
        "   - Call `check_oauth_status(patron_npub=<your_npub>)` to confirm session activation\n\n"
        "   **Option B — Manual Secure Courier:**\n"
        "   - Get your **patron npub** from the dpyc-oracle's how_to_join() tool\n"
        "   - Call `request_credential_channel(recipient_npub=<patron_npub>)` "
        "to receive a welcome DM\n"
        '   - Reply with JSON: `{"token_json": "...", "account_hash": "..."}`\n'
        "   - Call `receive_credentials(sender_npub=<patron_npub>)` to vault your credentials\n\n"
        "## Credits Model\n\n"
        "Tool calls cost api_sats per call. Auth and balance tools are always free. "
        "Use `check_balance` to see your balance. Top up via `purchase_credits`.\n\n"
        "## History Endpoints\n\n"
        "Order and transaction history are available via `get_orders`, `get_order`, "
        "`get_transactions`, and `get_transaction`. These cost 15 api_sats (list) "
        "or 8 api_sats (single) due to heavier data retrieval. "
        "Default lookback is 30 days."
    ),
)
tool = make_slug_tool(mcp, "schwab")

# ---------------------------------------------------------------------------
# Onboarding guidance for AI agents (no pricing-studio needed)
# ---------------------------------------------------------------------------

_ONBOARDING_NEXT_STEPS = {
    "action": "secure_courier_onboarding",
    "operator_setup": (
        "The operator must first deliver Schwab API app credentials via "
        'Secure Courier (service="schwab-operator"): '
        '{"app_key": "...", "secret": "..."}. '
        "This is a one-time setup per deployment."
    ),
    "step_1": (
        "Ask the user for their **patron npub** (the npub they registered "
        "as a DPYC Citizen). They can get one from the dpyc-oracle's "
        "how_to_join() tool."
    ),
    "step_2": (
        "Call request_credential_channel(recipient_npub=<npub>) to send "
        "a welcome DM to the user's Nostr client."
    ),
    "step_3": (
        "Tell the user to open their Nostr client (Primal, Damus, etc.) "
        "and reply to the welcome DM with their Schwab credentials in "
        "the format shown. Credentials must NEVER appear in this chat."
    ),
    "step_4": (
        "Once the user confirms they replied, call "
        "receive_credentials(sender_npub=<npub>) to vault the "
        "credentials for future sessions."
    ),
}

# ---------------------------------------------------------------------------
# Tool cost table (domain tools only — standard tool costs are in the runtime)
# ---------------------------------------------------------------------------

TOOL_COSTS: dict[str, int] = {
    # Domain-specific free
    "begin_oauth": ToolTier.FREE,
    "check_oauth_status": ToolTier.FREE,
    # Paid — WRITE tier (5 api_sats)
    "get_positions": ToolTier.WRITE,
    "get_balances": ToolTier.WRITE,
    "get_quote": ToolTier.WRITE,
    "get_movers": ToolTier.WRITE,
    "get_market_hours": ToolTier.WRITE,
    "search_instruments": ToolTier.WRITE,
    # Paid — HEAVY tier (10 api_sats)
    "get_option_chain": ToolTier.HEAVY,
    "get_price_history": ToolTier.HEAVY,
    # Paid — history endpoints (higher cost for multi-record scans)
    "get_orders": 15,
    "get_order": 8,
    "get_transactions": 15,
    "get_transaction": 8,
}

# Patron credentials use OAuth2 browser dance, not Secure Courier
PATRON_CREDENTIAL_SERVICE = "schwab"


# ---------------------------------------------------------------------------
# Settings singleton
# ---------------------------------------------------------------------------

_settings = None


def _get_settings():
    """Get or create the Settings singleton."""
    global _settings
    if _settings is not None:
        return _settings
    from settings import Settings

    _settings = Settings()
    return _settings


# ---------------------------------------------------------------------------
# OperatorRuntime — replaces all DPYC boilerplate
# ---------------------------------------------------------------------------

runtime = OperatorRuntime(
    service_name="Schwab MCP",
    tool_costs=TOOL_COSTS,
    operator_credential_template=CredentialTemplate(
        service="schwab-operator",
        version=2,
        fields={
            "btcpay_host": FieldSpec(
                required=True, sensitive=True,
                description="The URL of your BTCPay Server instance (e.g. https://btcpay.example.com).",
            ),
            "btcpay_api_key": FieldSpec(
                required=True, sensitive=True,
                description=(
                    "Your BTCPay Server API key. Generate one in BTCPay "
                    "under Account > Manage Account > API Keys."
                ),
            ),
            "btcpay_store_id": FieldSpec(
                required=True, sensitive=True,
                description=(
                    "Your BTCPay Store ID. Find it in BTCPay "
                    "under Stores > Settings > General."
                ),
            ),
            "app_key": FieldSpec(
                required=True, sensitive=True,
                description=(
                    "Your Schwab Trader API app key (client_id). "
                    "From the Schwab Developer Portal."
                ),
            ),
            "secret": FieldSpec(
                required=True, sensitive=True,
                description=(
                    "Your Schwab Trader API secret (client_secret). "
                    "From the Schwab Developer Portal."
                ),
            ),
        },
        description="Operator credentials for BTCPay Lightning payments and Schwab API access",
    ),
    # No patron_credential_template — Schwab uses OAuth2 browser dance
    operator_credential_greeting=(
        "Hi — I'm Schwab MCP, a Tollbooth service for read-only Schwab "
        "brokerage data. To come online, I need your BTCPay Server "
        "credentials and Schwab API app credentials."
    ),
)

# ---------------------------------------------------------------------------
# Register all standard DPYC tools from the wheel
# ---------------------------------------------------------------------------

def _get_version() -> str:
    try:
        import importlib.metadata
        return importlib.metadata.version("schwab-mcp")
    except Exception:
        return "unknown"


register_standard_tools(
    mcp,
    "schwab",
    runtime,
    service_name="schwab-mcp",
    service_version=_get_version(),
)


# ---------------------------------------------------------------------------
# Operator credential cache (delivered via Secure Courier)
# ---------------------------------------------------------------------------

_operator_credentials: dict[str, str] | None = None

# Well-known binding ID for operator credential session binding.
_OPERATOR_BINDING_ID = "__schwab_operator__"


async def _ensure_operator_credentials() -> dict[str, str]:
    """Return cached operator credentials, restoring from vault on cold start.

    Raises ValueError if operator credentials have not been delivered.
    """
    global _operator_credentials
    if _operator_credentials:
        return _operator_credentials

    # Try loading from runtime credential vault
    try:
        creds = await runtime.load_credentials(["app_key", "secret"])
        if creds.get("app_key") and creds.get("secret"):
            _operator_credentials = {
                "client_id": creds["app_key"],
                "client_secret": creds["secret"],
            }
            logger.info("Operator credentials restored from vault.")
            return _operator_credentials
    except Exception as exc:
        logger.debug("Operator credential restore failed: %s", exc)

    raise ValueError(
        "Schwab operator credentials not configured. "
        "The operator must deliver app_key and secret via "
        "Secure Courier (service='schwab-operator')."
    )


# ---------------------------------------------------------------------------
# Horizon auth helpers
# ---------------------------------------------------------------------------


def _get_current_user_id() -> str | None:
    """Extract FastMCP Cloud user ID from request headers."""
    try:
        from fastmcp.server.dependencies import get_http_headers

        headers = get_http_headers(include_all=True)
        return headers.get("fastmcp-cloud-user")
    except Exception:
        return None


def _require_user_id() -> str:
    """Extract user ID or raise ValueError."""
    user_id = _get_current_user_id()
    if not user_id:
        raise ValueError(
            "Multi-tenant credentials require FastMCP Cloud (Horizon). "
            "In local dev mode, the server cannot resolve a user identity."
        )
    return user_id


async def _get_redirect_uri() -> str:
    """Return the OAuth redirect URI from the DPYC registry."""
    from tollbooth import resolve_service_by_name

    try:
        svc = await resolve_service_by_name("tollbooth-oauth2-callback")
        return svc["url"]
    except Exception as exc:
        raise RuntimeError(
            f"Failed to resolve OAuth2 callback from registry: {exc}"
        ) from exc


# ---------------------------------------------------------------------------
# Session resolution helpers
# ---------------------------------------------------------------------------

# Horizon user_id → patron npub mapping (populated on OAuth success)
_npub_for_user: dict[str, str] = {}


async def _restore_session_from_vault(
    user_id: str, patron_npub: str,
):
    """Try to restore a patron session from the Neon vault."""
    creds = await runtime.load_patron_session(
        patron_npub, service=PATRON_CREDENTIAL_SERVICE,
    )
    if not creds or "token_json" not in creds:
        return None
    try:
        op_creds = await _ensure_operator_credentials()
        settings = _get_settings()
        from vault import _create_client, set_session
        client = _create_client(
            op_creds["client_id"],
            op_creds["client_secret"],
            creds["token_json"],
            api_base=settings.schwab_trader_api,
        )
        session = set_session(
            user_id,
            creds["token_json"],
            creds.get("account_hash", ""),
            client,
            npub=patron_npub,
        )
        _npub_for_user[user_id] = patron_npub
        logger.info("Restored session for %s from vault.", patron_npub[:20])
        return session
    except Exception as exc:
        logger.warning("Vault session restore failed: %s", exc)
        return None


async def _require_session(user_id: str, npub: str = ""):
    """Get per-user session, restoring from vault on cold start."""
    from vault import get_session

    session = get_session(user_id)
    if session is not None:
        return session

    # Try vault restoration (survives process restarts)
    patron_npub = _npub_for_user.get(user_id) or npub
    if patron_npub:
        restored = await _restore_session_from_vault(user_id, patron_npub)
        if restored is not None:
            return restored

    raise ValueError(
        "No active Schwab session. Use begin_oauth or receive_credentials "
        "to authenticate."
    )


async def _seed_balance(npub: str) -> bool:
    """Apply seed balance for a new user (idempotent via sentinel)."""
    settings = _get_settings()
    if settings.seed_balance_sats <= 0:
        return False
    try:
        cache = await runtime.ledger_cache()
        ledger = await cache.get(npub)
        sentinel = "seed_balance_v1"
        if sentinel not in ledger.credited_invoices:
            ledger.credit_deposit(settings.seed_balance_sats, sentinel)
            cache.mark_dirty(npub)
            await cache.flush_user(npub)
            return True
    except Exception:
        pass
    return False


# ---------------------------------------------------------------------------
# OAuth collector helper
# ---------------------------------------------------------------------------


async def _check_oauth_via_collector(user_id: str, patron_npub: str) -> dict[str, Any]:
    """Poll the external OAuth2 collector for the auth code, then activate session."""
    from oauth_flow import (
        exchange_code_for_token,
        fetch_account_hash,
        retrieve_code_from_collector,
    )

    try:
        from tollbooth.registry import DEFAULT_REGISTRY_URL, DPYCRegistry

        settings = _get_settings()
        registry = DPYCRegistry(
            url=DEFAULT_REGISTRY_URL,
            cache_ttl_seconds=settings.dpyc_registry_cache_ttl_seconds,
        )
        try:
            svc = await registry.resolve_service_by_name("tollbooth-oauth2-collector")
        finally:
            await registry.close()
        collector_url = svc["url"].rstrip("/")
    except Exception as e:
        return {"success": False, "error": f"Failed to resolve OAuth2 collector: {e}"}

    code = await retrieve_code_from_collector(collector_url, patron_npub)
    if code is None:
        return {
            "status": "pending",
            "message": "Waiting for browser authorization. Open the URL from begin_oauth.",
        }

    # Exchange code for token
    try:
        op_creds = await _ensure_operator_credentials()
    except ValueError as e:
        return {"success": False, "error": str(e)}

    redirect_uri = await _get_redirect_uri()

    try:
        token = await exchange_code_for_token(
            code=code,
            client_id=op_creds["client_id"],
            client_secret=op_creds["client_secret"],
            redirect_uri=redirect_uri,
        )
        account_hash = await fetch_account_hash(token["access_token"])
    except Exception as exc:
        return {"status": "failed", "error": str(exc)}

    # Activate session
    import json

    from vault import _create_client, set_session

    settings = _get_settings()
    token_json = json.dumps(token)
    client = _create_client(
        op_creds["client_id"],
        op_creds["client_secret"],
        token_json,
        api_base=settings.schwab_trader_api,
    )
    set_session(user_id, token_json, account_hash, client, npub=patron_npub)
    _npub_for_user[user_id] = patron_npub

    # Persist to vault for cross-restart restoration
    await runtime.store_patron_session(patron_npub, {
        "token_json": token_json,
        "account_hash": account_hash,
    }, service=PATRON_CREDENTIAL_SERVICE)

    # Seed balance for new users
    await _seed_balance(patron_npub)

    return {"status": "completed", "message": "Session activated successfully."}


# ---------------------------------------------------------------------------
# MCP Tools — OAuth Flow (Free, domain-specific)
# ---------------------------------------------------------------------------


@tool
async def begin_oauth(patron_npub: str) -> dict[str, Any]:
    """Start the OAuth2 authorization flow to connect your Schwab account.

    Returns an authorization URL -- open it in your browser to log in to
    Schwab and authorize. After authorizing, call check_oauth_status with
    the same patron_npub to confirm your session is active.

    Args:
        patron_npub: Your DPYC patron Nostr public key (npub1...).
    """
    try:
        op_creds = await _ensure_operator_credentials()
    except ValueError as e:
        return {"success": False, "error": str(e)}

    try:
        redirect_uri = await _get_redirect_uri()
    except RuntimeError as e:
        return {"success": False, "error": str(e)}

    from oauth_flow import begin_oauth_flow

    result = begin_oauth_flow(
        patron_npub=patron_npub,
        client_id=op_creds["client_id"],
        redirect_uri=redirect_uri,
    )

    # Shorten the authorize URL for human-friendliness (best-effort)
    # Shorten the authorize URL for easier copy/paste
    if "authorize_url" in result:
        try:
            import httpx

            resp = await httpx.AsyncClient().post(
                "https://v.gd/create.php",
                params={"format": "simple", "url": result["authorize_url"]},
                timeout=5,
            )
            if resp.status_code == 200 and resp.text.startswith("https://"):
                result["authorize_url_short"] = resp.text.strip()
        except Exception:
            pass  # Full URL is always available

    return result


@tool
async def check_oauth_status(patron_npub: str) -> dict[str, Any]:
    """Check whether your OAuth authorization flow has completed.

    Call this after opening the authorization URL from begin_oauth
    and completing the Schwab login in your browser.

    Args:
        patron_npub: The same DPYC patron npub used in begin_oauth.
    """
    try:
        user_id = _require_user_id()
    except ValueError as e:
        return {"success": False, "error": str(e)}

    return await _check_oauth_via_collector(user_id, patron_npub)


# ---------------------------------------------------------------------------
# MCP Tools — Paid (Schwab brokerage data, domain-specific)
# ---------------------------------------------------------------------------


@tool
async def get_positions(npub: str = "") -> str | dict[str, Any]:
    """Get positions for a Schwab account. Requires npub for credit billing.

    Costs 5 api_sats.

    Args:
        npub: Your DPYC patron Nostr public key (npub1...) for credit attribution.
    """
    err = await runtime.debit_or_error("get_positions", npub)
    if err:
        return err

    try:
        user_id = _require_user_id()
        session = await _require_session(user_id, npub=npub)
    except ValueError as e:
        await runtime.rollback_debit("get_positions", npub)
        return {"success": False, "error": str(e)}

    try:
        from tools.account import get_positions as _get_positions

        return await _get_positions(session.client, session.account_hash)
    except Exception:
        await runtime.rollback_debit("get_positions", npub)
        raise


@tool
async def get_balances(npub: str = "") -> str | dict[str, Any]:
    """Get account balances for a Schwab account. Requires npub for credit billing.

    Costs 5 api_sats.

    Args:
        npub: Your DPYC patron Nostr public key (npub1...) for credit attribution.
    """
    err = await runtime.debit_or_error("get_balances", npub)
    if err:
        return err

    try:
        user_id = _require_user_id()
        session = await _require_session(user_id, npub=npub)
    except ValueError as e:
        await runtime.rollback_debit("get_balances", npub)
        return {"success": False, "error": str(e)}

    try:
        from tools.account import get_account_balances as _get_account_balances

        return await _get_account_balances(session.client, session.account_hash)
    except Exception:
        await runtime.rollback_debit("get_balances", npub)
        raise


@tool
async def get_quote(symbols: str, npub: str = "") -> str | dict[str, Any]:
    """Get real-time quotes for one or more symbols. Requires npub for credit billing.

    Costs 5 api_sats.

    Args:
        symbols: Comma-separated ticker symbols (e.g. "AAPL,MSFT,TSLA").
        npub: Your DPYC patron Nostr public key (npub1...) for credit attribution.
    """
    err = await runtime.debit_or_error("get_quote", npub)
    if err:
        return err

    try:
        user_id = _require_user_id()
        session = await _require_session(user_id, npub=npub)
    except ValueError as e:
        await runtime.rollback_debit("get_quote", npub)
        return {"success": False, "error": str(e)}

    try:
        from tools.market import get_quote as _get_quote

        return await _get_quote(session.client, symbols)
    except Exception:
        await runtime.rollback_debit("get_quote", npub)
        raise


@tool
async def get_option_chain(
    symbol: str,
    strike_count: int = 20,
    contract_type: str = "ALL",
    days_to_expiration: int = 21,
    npub: str = "",
) -> str | dict[str, Any]:
    """Get filtered option chain for spread evaluation. Requires npub for credit billing.

    Costs 10 api_sats.

    Args:
        symbol: Underlying ticker symbol.
        strike_count: Number of strikes around ATM to include.
        contract_type: "ALL", "CALL", or "PUT".
        days_to_expiration: Maximum days to expiration to include.
        npub: Your DPYC patron Nostr public key (npub1...) for credit attribution.
    """
    err = await runtime.debit_or_error("get_option_chain", npub)
    if err:
        return err

    try:
        user_id = _require_user_id()
        session = await _require_session(user_id, npub=npub)
    except ValueError as e:
        await runtime.rollback_debit("get_option_chain", npub)
        return {"success": False, "error": str(e)}

    try:
        from tools.options import get_option_chain as _get_option_chain

        return await _get_option_chain(
            session.client, symbol, strike_count, contract_type, days_to_expiration,
        )
    except Exception:
        await runtime.rollback_debit("get_option_chain", npub)
        raise


@tool
async def get_price_history(
    symbol: str,
    period_type: str = "month",
    period: int = 1,
    frequency_type: str = "daily",
    frequency: int = 1,
    npub: str = "",
) -> str | dict[str, Any]:
    """Get historical OHLCV price data for trend analysis. Requires npub for credit billing.

    Costs 10 api_sats.

    Args:
        symbol: Ticker symbol.
        period_type: "day", "month", "year", or "ytd".
        period: Number of periods.
        frequency_type: "minute", "daily", "weekly", or "monthly".
        frequency: Frequency interval.
        npub: Your DPYC patron Nostr public key (npub1...) for credit attribution.
    """
    err = await runtime.debit_or_error("get_price_history", npub)
    if err:
        return err

    try:
        user_id = _require_user_id()
        session = await _require_session(user_id, npub=npub)
    except ValueError as e:
        await runtime.rollback_debit("get_price_history", npub)
        return {"success": False, "error": str(e)}

    try:
        from tools.market import get_price_history as _get_price_history

        return await _get_price_history(
            session.client, symbol, period_type, period, frequency_type, frequency,
        )
    except Exception:
        await runtime.rollback_debit("get_price_history", npub)
        raise


@tool
async def get_movers(
    index: str = "$SPX",
    sort: str = "PERCENT_CHANGE_UP",
    frequency: int = 0,
    npub: str = "",
) -> str | dict[str, Any]:
    """Get top movers for a market index. Requires npub for credit billing.

    Costs 5 api_sats.

    Args:
        index: Index symbol -- "$DJI", "$COMPX", or "$SPX".
        sort: "PERCENT_CHANGE_UP", "PERCENT_CHANGE_DOWN", or "VOLUME".
        frequency: 0 = all, 1 = 1-5%, 2 = 5-10%, 3 = 10-20%, 4 = 20%+.
        npub: Your DPYC patron Nostr public key (npub1...) for credit attribution.
    """
    err = await runtime.debit_or_error("get_movers", npub)
    if err:
        return err

    try:
        user_id = _require_user_id()
        session = await _require_session(user_id, npub=npub)
    except ValueError as e:
        await runtime.rollback_debit("get_movers", npub)
        return {"success": False, "error": str(e)}

    try:
        from tools.market import get_movers as _get_movers

        return await _get_movers(session.client, index, sort, frequency)
    except Exception:
        await runtime.rollback_debit("get_movers", npub)
        raise


@tool
async def get_market_hours(
    markets: str = "equity,option",
    date: str = "",
    npub: str = "",
) -> str | dict[str, Any]:
    """Get market hours for equity, option, bond, future, or forex markets.

    Requires npub for credit billing.

    Costs 5 api_sats.

    Args:
        markets: Comma-separated: "equity", "option", "bond", "future", "forex".
        date: ISO date to check (e.g. "2026-03-15"). Defaults to today.
        npub: Your DPYC patron Nostr public key (npub1...) for credit attribution.
    """
    err = await runtime.debit_or_error("get_market_hours", npub)
    if err:
        return err

    try:
        user_id = _require_user_id()
        session = await _require_session(user_id, npub=npub)
    except ValueError as e:
        await runtime.rollback_debit("get_market_hours", npub)
        return {"success": False, "error": str(e)}

    try:
        from tools.market import get_market_hours as _get_market_hours

        return await _get_market_hours(
            session.client, markets, date=date or None,
        )
    except Exception:
        await runtime.rollback_debit("get_market_hours", npub)
        raise


@tool
async def search_instruments(
    symbol: str,
    projection: str = "symbol-search",
    npub: str = "",
) -> str | dict[str, Any]:
    """Search for instruments by symbol, name, or CUSIP. Requires npub for credit billing.

    Costs 5 api_sats.

    Args:
        symbol: Search term -- ticker, partial name, or CUSIP.
        projection: "symbol-search", "symbol-regex", "desc-search",
            "desc-regex", or "fundamental".
        npub: Your DPYC patron Nostr public key (npub1...) for credit attribution.
    """
    err = await runtime.debit_or_error("search_instruments", npub)
    if err:
        return err

    try:
        user_id = _require_user_id()
        session = await _require_session(user_id, npub=npub)
    except ValueError as e:
        await runtime.rollback_debit("search_instruments", npub)
        return {"success": False, "error": str(e)}

    try:
        from tools.market import search_instruments as _search_instruments

        return await _search_instruments(
            session.client, symbol, projection=projection,
        )
    except Exception:
        await runtime.rollback_debit("search_instruments", npub)
        raise


@tool
async def get_orders(
    from_date: str = "",
    to_date: str = "",
    status_filter: str = "",
    npub: str = "",
) -> str | dict[str, Any]:
    """Get order history for your Schwab account. Requires npub for credit billing.

    Costs 15 api_sats.

    Args:
        from_date: Start date (ISO 8601). Defaults to 30 days ago.
        to_date: End date (ISO 8601). Defaults to now.
        status_filter: Optional status filter (e.g. "FILLED", "CANCELED", "WORKING").
        npub: Your DPYC patron Nostr public key (npub1...) for credit attribution.
    """
    err = await runtime.debit_or_error("get_orders", npub)
    if err:
        return err

    try:
        user_id = _require_user_id()
        session = await _require_session(user_id, npub=npub)
    except ValueError as e:
        await runtime.rollback_debit("get_orders", npub)
        return {"success": False, "error": str(e)}

    try:
        from tools.account import get_orders as _get_orders

        return await _get_orders(
            session.client,
            session.account_hash,
            from_date=from_date or None,
            to_date=to_date or None,
            status_filter=status_filter or None,
        )
    except Exception:
        await runtime.rollback_debit("get_orders", npub)
        raise


@tool
async def get_order(order_id: str, npub: str = "") -> str | dict[str, Any]:
    """Get details for a single order by ID. Requires npub for credit billing.

    Costs 8 api_sats.

    Args:
        order_id: The Schwab order ID.
        npub: Your DPYC patron Nostr public key (npub1...) for credit attribution.
    """
    err = await runtime.debit_or_error("get_order", npub)
    if err:
        return err

    try:
        user_id = _require_user_id()
        session = await _require_session(user_id, npub=npub)
    except ValueError as e:
        await runtime.rollback_debit("get_order", npub)
        return {"success": False, "error": str(e)}

    try:
        from tools.account import get_order as _get_order

        return await _get_order(session.client, session.account_hash, order_id)
    except Exception:
        await runtime.rollback_debit("get_order", npub)
        raise


@tool
async def get_transactions(
    from_date: str = "",
    to_date: str = "",
    transaction_types: str = "",
    npub: str = "",
) -> str | dict[str, Any]:
    """Get transaction history for your Schwab account. Requires npub for credit billing.

    Costs 15 api_sats.

    Args:
        from_date: Start date (ISO 8601). Defaults to 30 days ago.
        to_date: End date (ISO 8601). Defaults to now.
        transaction_types: Comma-separated types: TRADE, DIVIDEND, CASH_IN_OR_CASH_OUT, etc.
        npub: Your DPYC patron Nostr public key (npub1...) for credit attribution.
    """
    err = await runtime.debit_or_error("get_transactions", npub)
    if err:
        return err

    try:
        user_id = _require_user_id()
        session = await _require_session(user_id, npub=npub)
    except ValueError as e:
        await runtime.rollback_debit("get_transactions", npub)
        return {"success": False, "error": str(e)}

    try:
        from tools.account import get_transactions as _get_transactions

        return await _get_transactions(
            session.client,
            session.account_hash,
            from_date=from_date or None,
            to_date=to_date or None,
            transaction_types=transaction_types or None,
        )
    except Exception:
        await runtime.rollback_debit("get_transactions", npub)
        raise


@tool
async def get_transaction(transaction_id: str, npub: str = "") -> str | dict[str, Any]:
    """Get details for a single transaction by ID. Requires npub for credit billing.

    Costs 8 api_sats.

    Args:
        transaction_id: The Schwab transaction ID.
        npub: Your DPYC patron Nostr public key (npub1...) for credit attribution.
    """
    err = await runtime.debit_or_error("get_transaction", npub)
    if err:
        return err

    try:
        user_id = _require_user_id()
        session = await _require_session(user_id, npub=npub)
    except ValueError as e:
        await runtime.rollback_debit("get_transaction", npub)
        return {"success": False, "error": str(e)}

    try:
        from tools.account import get_transaction as _get_transaction

        return await _get_transaction(
            session.client, session.account_hash, transaction_id,
        )
    except Exception:
        await runtime.rollback_debit("get_transaction", npub)
        raise


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    from tollbooth import validate_operator_tools

    missing = validate_operator_tools(mcp, "schwab")
    if missing:
        import sys

        print(f"\u26a0 Missing base-catalog tools: {', '.join(missing)}", file=sys.stderr)
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8000)
