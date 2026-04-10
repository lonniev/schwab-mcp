"""Schwab MCP Server — multi-tenant brokerage data for Claude.ai.

Tollbooth-monetized, DPYC-native. Standard DPYC tools (check_balance,
purchase_credits, Secure Courier, Oracle, pricing) are provided by
``register_standard_tools`` from the tollbooth-dpyc wheel. Only
domain-specific Schwab brokerage tools are defined here.
"""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastmcp import FastMCP
from pydantic import Field
from tollbooth.credential_templates import CredentialTemplate, FieldSpec
from tollbooth.runtime import OperatorRuntime, register_standard_tools
from tollbooth.slug_tools import make_slug_tool
from tollbooth.tool_identity import STANDARD_IDENTITIES, ToolIdentity, capability_uuid

logger = logging.getLogger(__name__)

# Shared npub field annotation — avoids E501 on every tool signature
NpubField = Annotated[
    str,
    Field(
        description="Required. Your Nostr public key (npub1...) "
        "for credit billing."
    ),
]

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
        "Tool calls are priced dynamically via the operator's pricing model. "
        "Use `check_balance` to see your balance and `check_price` to preview "
        "tool costs. Top up via `purchase_credits`.\n\n"
        "## History Endpoints\n\n"
        "Order and transaction history are available via `get_orders`, `get_order`, "
        "`get_transactions`, and `get_transaction`. Default lookback is 30 days."
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
# Tool registry (domain tools only — standard tools are in the wheel)
# ---------------------------------------------------------------------------

_DOMAIN_TOOLS = [
    # Domain-specific free
    ToolIdentity(
        capability="begin_oauth",
        category="free",
        intent="Start OAuth2 browser flow to connect a Schwab brokerage account.",
    ),
    ToolIdentity(
        capability="check_oauth_status",
        category="free",
        intent="Check whether the Schwab OAuth authorization flow has completed.",
    ),
    # Paid — write tier (brokerage reads)
    ToolIdentity(
        capability="get_brokerage_positions",
        category="write",
        intent="Get positions for a Schwab brokerage account.",
    ),
    ToolIdentity(
        capability="get_brokerage_balances",
        category="write",
        intent="Get account balances for a Schwab brokerage account.",
    ),
    ToolIdentity(
        capability="get_stock_quote",
        category="write",
        intent="Get real-time quotes for one or more ticker symbols.",
    ),
    ToolIdentity(
        capability="get_market_movers",
        category="write",
        intent="Get top movers for a market index.",
    ),
    ToolIdentity(
        capability="get_market_hours",
        category="write",
        intent="Get trading hours for equity, option, and other markets.",
    ),
    ToolIdentity(
        capability="search_instruments",
        category="write",
        intent="Search for instruments by symbol, name, or CUSIP.",
    ),
    # Paid — heavy tier (complex data retrieval)
    ToolIdentity(
        capability="get_option_chain",
        category="heavy",
        intent="Get filtered option chain for spread evaluation.",
    ),
    ToolIdentity(
        capability="get_price_history",
        category="heavy",
        intent="Get historical OHLCV price data for trend analysis.",
    ),
    # Paid — heavy tier (multi-record history scans)
    ToolIdentity(
        capability="get_brokerage_orders",
        category="heavy",
        intent="Get order history for a Schwab brokerage account.",
    ),
    ToolIdentity(
        capability="get_brokerage_order",
        category="heavy",
        intent="Get details for a single order by ID.",
    ),
    ToolIdentity(
        capability="get_brokerage_transactions",
        category="heavy",
        intent="Get transaction history for a Schwab brokerage account.",
    ),
    ToolIdentity(
        capability="get_brokerage_transaction",
        category="heavy",
        intent="Get details for a single transaction by ID.",
    ),
]

TOOL_REGISTRY: dict[str, ToolIdentity] = {ti.tool_id: ti for ti in _DOMAIN_TOOLS}

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
    tool_registry={**STANDARD_IDENTITIES, **TOOL_REGISTRY},
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
# Schwab OAuth2 helpers
# ---------------------------------------------------------------------------




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

# Session user_id → patron npub mapping (populated on Schwab OAuth success)
_npub_for_user: dict[str, str] = {}


async def _restore_session_from_vault(
    user_id: str, patron_npub: str,
) -> tuple[Any, str]:
    """Attempt to restore a patron session from the encrypted vault.

    Returns (session, "") on success, or (None, situation) describing
    which lifecycle state the system is in. These are expected states,
    not errors — each has a clear next action.
    """
    # Stage 1: Can we reach the vault?
    try:
        creds = await runtime.load_patron_session(
            patron_npub, service=PATRON_CREDENTIAL_SERVICE,
        )
    except Exception:
        return None, "vault_bootstrapping"

    # Stage 2: Does this patron have stored credentials?
    if not creds or "token_json" not in creds:
        return None, "no_credentials"

    # Stage 3: Can we build a live Schwab client from stored credentials?
    try:
        op_creds = await _ensure_operator_credentials()
    except Exception:
        return None, "operator_not_configured"

    try:
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
        return session, ""
    except Exception:
        return None, "token_expired"


# Patron-facing guidance for each lifecycle state.
_SESSION_GUIDANCE: dict[str, str] = {
    "vault_bootstrapping": (
        "The server is establishing its encrypted connection to the "
        "credential vault. This happens once after a cold start and "
        "typically completes within 10-15 seconds. "
        "Action: repeat your request shortly — no re-authentication needed."
    ),
    "operator_not_configured": (
        "The operator's Schwab API application credentials have not been "
        "delivered yet. This is an operator setup step, not a patron action. "
        "The operator needs to complete Secure Courier onboarding with their "
        "Schwab app_key and secret. "
        "Action: contact the operator or try again later."
    ),
    "token_expired": (
        "Your Schwab OAuth session was found in the vault but the access "
        "token could not be used — Schwab limits tokens to 7 days. "
        "Action: call begin_oauth to complete a new Schwab authorization. "
        "This is a one-time browser sign-in that refreshes your access."
    ),
    "no_credentials": (
        "No Schwab credentials are stored for your identity. This is "
        "expected on first use. "
        "Action: call begin_oauth to link your Schwab account through a "
        "secure browser-based authorization. Your credentials will be "
        "encrypted and stored so future sessions restore automatically."
    ),
}


async def _require_session(user_id: str, npub: str = ""):
    """Get per-user session, restoring from vault on cold start."""
    from vault import get_session

    session = get_session(user_id)
    if session is not None:
        return session

    # Try vault restoration (survives process restarts)
    patron_npub = _npub_for_user.get(user_id) or npub
    situation = "no_credentials"
    if patron_npub:
        restored, situation = await _restore_session_from_vault(user_id, patron_npub)
        if restored is not None:
            return restored

    guidance = _SESSION_GUIDANCE.get(situation, _SESSION_GUIDANCE["no_credentials"])
    raise ValueError(guidance)


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
        from tollbooth.registry import resolve_service_by_name

        settings = _get_settings()
        svc = await resolve_service_by_name(
            "tollbooth-oauth2-collector",
            cache_ttl_seconds=settings.dpyc_registry_cache_ttl_seconds,
        )
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

    # Shorten the authorize URL via tollbooth-shortlinks (best-effort)
    if "authorize_url" in result:
        from tollbooth.shortlinks import create_shortlink as _create_shortlink

        short = await _create_shortlink(result["authorize_url"])
        if short:
            result["authorize_url_short"] = short

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
        user_id = OperatorRuntime.require_user_id()
    except ValueError as e:
        return {"success": False, "error": str(e)}

    return await _check_oauth_via_collector(user_id, patron_npub)


# ---------------------------------------------------------------------------
# MCP Tools — Paid (Schwab brokerage data, domain-specific)
# ---------------------------------------------------------------------------


@tool
@runtime.paid_tool(capability_uuid("get_brokerage_positions"), catch_errors=True)
async def get_brokerage_positions(npub: NpubField = "") -> str | dict[str, Any]:
    """Get positions for a Schwab account.
    Args:
        npub: Your DPYC patron Nostr public key (npub1...) for credit attribution.
    """
    user_id = OperatorRuntime.require_user_id()
    session = await _require_session(user_id, npub=npub)
    from tools.account import get_positions as _get_positions

    return await _get_positions(session.client, session.account_hash)


@tool
@runtime.paid_tool(capability_uuid("get_brokerage_balances"), catch_errors=True)
async def get_brokerage_balances(npub: NpubField = "") -> str | dict[str, Any]:
    """Get account balances for a Schwab account.
    Args:
        npub: Your DPYC patron Nostr public key (npub1...) for credit attribution.
    """
    user_id = OperatorRuntime.require_user_id()
    session = await _require_session(user_id, npub=npub)
    from tools.account import get_account_balances as _get_account_balances

    return await _get_account_balances(session.client, session.account_hash)


@tool
@runtime.paid_tool(capability_uuid("get_stock_quote"), catch_errors=True)
async def get_stock_quote(symbols: str, npub: NpubField = "") -> str | dict[str, Any]:
    """Get real-time quotes for one or more symbols.
    Args:
        symbols: Comma-separated ticker symbols (e.g. "AAPL,MSFT,TSLA").
        npub: Your DPYC patron Nostr public key (npub1...) for credit attribution.
    """
    user_id = OperatorRuntime.require_user_id()
    session = await _require_session(user_id, npub=npub)
    from tools.market import get_quote as _get_quote

    return await _get_quote(session.client, symbols)


@tool
@runtime.paid_tool(capability_uuid("get_option_chain"), catch_errors=True)
async def get_option_chain(
    symbol: str,
    strike_count: int = 20,
    contract_type: str = "ALL",
    days_to_expiration: int = 21,
    npub: NpubField = "",
) -> str | dict[str, Any]:
    """Get filtered option chain for spread evaluation.
    Args:
        symbol: Underlying ticker symbol.
        strike_count: Number of strikes around ATM to include.
        contract_type: "ALL", "CALL", or "PUT".
        days_to_expiration: Maximum days to expiration to include.
        npub: Your DPYC patron Nostr public key (npub1...) for credit attribution.
    """
    user_id = OperatorRuntime.require_user_id()
    session = await _require_session(user_id, npub=npub)
    from tools.options import get_option_chain as _get_option_chain

    return await _get_option_chain(
        session.client, symbol, strike_count, contract_type, days_to_expiration,
    )


@tool
@runtime.paid_tool(capability_uuid("get_price_history"), catch_errors=True)
async def get_price_history(
    symbol: str,
    period_type: str = "month",
    period: int = 1,
    frequency_type: str = "daily",
    frequency: int = 1,
    npub: NpubField = "",
) -> str | dict[str, Any]:
    """Get historical OHLCV price data for trend analysis.
    Args:
        symbol: Ticker symbol.
        period_type: "day", "month", "year", or "ytd".
        period: Number of periods.
        frequency_type: "minute", "daily", "weekly", or "monthly".
        frequency: Frequency interval.
        npub: Your DPYC patron Nostr public key (npub1...) for credit attribution.
    """
    user_id = OperatorRuntime.require_user_id()
    session = await _require_session(user_id, npub=npub)
    from tools.market import get_price_history as _get_price_history

    return await _get_price_history(
        session.client, symbol, period_type, period, frequency_type, frequency,
    )


@tool
@runtime.paid_tool(capability_uuid("get_market_movers"), catch_errors=True)
async def get_market_movers(
    index: str = "$SPX",
    sort: str = "PERCENT_CHANGE_UP",
    frequency: int = 0,
    npub: NpubField = "",
) -> str | dict[str, Any]:
    """Get top movers for a market index.
    Args:
        index: Index symbol -- "$DJI", "$COMPX", or "$SPX".
        sort: "PERCENT_CHANGE_UP", "PERCENT_CHANGE_DOWN", or "VOLUME".
        frequency: 0 = all, 1 = 1-5%, 2 = 5-10%, 3 = 10-20%, 4 = 20%+.
        npub: Your DPYC patron Nostr public key (npub1...) for credit attribution.
    """
    user_id = OperatorRuntime.require_user_id()
    session = await _require_session(user_id, npub=npub)
    from tools.market import get_movers as _get_movers

    return await _get_movers(session.client, index, sort, frequency)


@tool
@runtime.paid_tool(capability_uuid("get_market_hours"), catch_errors=True)
async def get_market_hours(
    markets: str = "equity,option",
    date: str = "",
    npub: NpubField = "",
) -> str | dict[str, Any]:
    """Get market hours for equity, option, bond, future, or forex markets.

    Args:
        markets: Comma-separated: "equity", "option", "bond", "future", "forex".
        date: ISO date to check (e.g. "2026-03-15"). Defaults to today.
        npub: Your DPYC patron Nostr public key (npub1...) for credit attribution.
    """
    user_id = OperatorRuntime.require_user_id()
    session = await _require_session(user_id, npub=npub)
    from tools.market import get_market_hours as _get_market_hours

    return await _get_market_hours(
        session.client, markets, date=date or None,
    )


@tool
@runtime.paid_tool(capability_uuid("search_instruments"), catch_errors=True)
async def search_instruments(
    symbol: str,
    projection: str = "symbol-search",
    npub: NpubField = "",
) -> str | dict[str, Any]:
    """Search for instruments by symbol, name, or CUSIP.
    Args:
        symbol: Search term -- ticker, partial name, or CUSIP.
        projection: "symbol-search", "symbol-regex", "desc-search",
            "desc-regex", or "fundamental".
        npub: Your DPYC patron Nostr public key (npub1...) for credit attribution.
    """
    user_id = OperatorRuntime.require_user_id()
    session = await _require_session(user_id, npub=npub)
    from tools.market import search_instruments as _search_instruments

    return await _search_instruments(
        session.client, symbol, projection=projection,
    )


@tool
@runtime.paid_tool(capability_uuid("get_brokerage_orders"), catch_errors=True)
async def get_brokerage_orders(
    from_date: str = "",
    to_date: str = "",
    status_filter: str = "",
    npub: NpubField = "",
) -> str | dict[str, Any]:
    """Get order history for your Schwab account.
    Args:
        from_date: Start date (ISO 8601). Defaults to 30 days ago.
        to_date: End date (ISO 8601). Defaults to now.
        status_filter: Optional status filter (e.g. "FILLED", "CANCELED", "WORKING").
        npub: Your DPYC patron Nostr public key (npub1...) for credit attribution.
    """
    user_id = OperatorRuntime.require_user_id()
    session = await _require_session(user_id, npub=npub)
    from tools.account import get_orders as _get_orders

    return await _get_orders(
        session.client,
        session.account_hash,
        from_date=from_date or None,
        to_date=to_date or None,
        status_filter=status_filter or None,
    )


@tool
@runtime.paid_tool(capability_uuid("get_brokerage_order"), catch_errors=True)
async def get_brokerage_order(order_id: str, npub: NpubField = "") -> str | dict[str, Any]:
    """Get details for a single order by ID.
    Args:
        order_id: The Schwab order ID.
        npub: Your DPYC patron Nostr public key (npub1...) for credit attribution.
    """
    user_id = OperatorRuntime.require_user_id()
    session = await _require_session(user_id, npub=npub)
    from tools.account import get_order as _get_order

    return await _get_order(session.client, session.account_hash, order_id)


@tool
@runtime.paid_tool(capability_uuid("get_brokerage_transactions"), catch_errors=True)
async def get_brokerage_transactions(
    from_date: str = "",
    to_date: str = "",
    transaction_types: str = "",
    npub: NpubField = "",
) -> str | dict[str, Any]:
    """Get transaction history for your Schwab account.
    Args:
        from_date: Start date (ISO 8601). Defaults to 30 days ago.
        to_date: End date (ISO 8601). Defaults to now.
        transaction_types: Comma-separated types: TRADE, DIVIDEND, CASH_IN_OR_CASH_OUT, etc.
        npub: Your DPYC patron Nostr public key (npub1...) for credit attribution.
    """
    user_id = OperatorRuntime.require_user_id()
    session = await _require_session(user_id, npub=npub)
    from tools.account import get_transactions as _get_transactions

    return await _get_transactions(
        session.client,
        session.account_hash,
        from_date=from_date or None,
        to_date=to_date or None,
        transaction_types=transaction_types or None,
    )


@tool
@runtime.paid_tool(capability_uuid("get_brokerage_transaction"), catch_errors=True)
async def get_brokerage_transaction(
    transaction_id: str, npub: NpubField = "",
) -> str | dict[str, Any]:
    """Get details for a single transaction by ID.
    Args:
        transaction_id: The Schwab transaction ID.
        npub: Your DPYC patron Nostr public key (npub1...) for credit attribution.
    """
    user_id = OperatorRuntime.require_user_id()
    session = await _require_session(user_id, npub=npub)
    from tools.account import get_transaction as _get_transaction

    return await _get_transaction(
        session.client, session.account_hash, transaction_id,
    )


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
