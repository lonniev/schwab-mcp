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
from tollbooth.credential_validators import validate_btcpay_creds, validate_required
from tollbooth.oauth_config import OAuthProviderConfig
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
        "3. **Patron onboarding** (per-user):\n"
        "   - Call `begin_oauth(npub=<your_npub>)` to get an authorization URL\n"
        "   - Open the URL in your browser and log in to Schwab\n"
        "   - Call `check_oauth_status(npub=<your_npub>)` to confirm session activation\n"
        "   - Call `get_account_numbers(npub=<your_npub>)` to see your accounts\n"
        "   - Call `update_patron_credential(npub=<your_npub>, "
        'field="account_hash", value=<hash>)` to set your preferred account\n\n'
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
    "action": "oauth_onboarding",
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
        "Call begin_oauth(npub=<npub>) to get an authorization URL. "
        "The user opens it in their browser and logs in to Schwab."
    ),
    "step_3": (
        "Call check_oauth_status(npub=<npub>) to confirm authorization. "
        "Then call get_account_numbers(npub=<npub>) to list accounts."
    ),
    "step_4": (
        "Call update_patron_credential(npub=<npub>, "
        'field="account_hash", value=<hash>) to set the preferred account.'
    ),
}

# ---------------------------------------------------------------------------
# Tool registry (domain tools only — standard tools are in the wheel)
# ---------------------------------------------------------------------------

_DOMAIN_TOOLS = [
    # OAuth tools are now standard (from wheel via OAuthProviderConfig)
    # Free — account discovery (no account_hash needed)
    ToolIdentity(
        capability="get_account_numbers",
        category="free",
        intent="List Schwab account numbers and hash identifiers.",
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
    oauth_provider=OAuthProviderConfig(
        authorize_url="https://api.schwabapi.com/v1/oauth/authorize",
        token_url="https://api.schwabapi.com/v1/oauth/token",
        scopes="",
        pkce=False,
        service_name="schwab",
        client_id_field="app_key",
        client_secret_field="secret",
    ),
    operator_credential_greeting=(
        "Hi — I'm Schwab MCP, a Tollbooth service for read-only Schwab "
        "brokerage data. To come online, I need your BTCPay Server "
        "credentials and Schwab API app credentials."
    ),
    credential_validator=lambda creds: (
        validate_btcpay_creds(creds)
        + [e for e in [validate_required(creds.get("app_key", ""), "app_key")] if e]
        + [e for e in [validate_required(creds.get("secret", ""), "secret")] if e]
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




# ---------------------------------------------------------------------------
# Session resolution helpers
# ---------------------------------------------------------------------------

# Session user_id → patron npub mapping (populated on Schwab OAuth success)
# Session identity is now npub-only — no Horizon user_id mapping needed.


# Schwab's only operator-specific situation: the patron has authorized
# OAuth but has not yet selected an account_hash for brokerage calls.
# Everything else (token_expired, no_credentials, vault_bootstrapping,
# operator_not_configured, no_oauth_config, *unknown*) is delegated to
# runtime.oauth_situation_response — one canonical mapping in the wheel.
# npub validation also lives in the wheel via runtime.npub_validation_error.
_SCHWAB_SITUATIONS: dict[str, dict[str, Any]] = {
    "no_account_hash": {
        "error_code": "account_hash_required",
        "error": (
            "You have multiple Schwab accounts and none is selected as the "
            "default. (Single-account patrons are auto-selected; this only "
            "fires when explicit choice is required.)"
        ),
        "next_steps": [
            "schwab_get_account_numbers(npub=<patron_npub>) to list your accounts",
            'schwab_update_patron_credential(npub=<patron_npub>, field="account_hash", value=<hash>) to record your choice',
            "Retry the original tool call — selection persists across operator restarts",
        ],
    },
}


def _resolution_for(situation: str) -> dict[str, Any]:
    """Build a structured error response for a session-restoration situation.

    Schwab-specific situations (account_hash_required) are handled
    inline; everything else delegates to the wheel's standard OAuth
    situation mapping.
    """
    if situation in _SCHWAB_SITUATIONS:
        return {"success": False, **_SCHWAB_SITUATIONS[situation]}
    return runtime.oauth_situation_response(situation)


async def _try_auto_select_account_hash(
    npub: str, creds: dict[str, Any],
) -> str | None:
    """If the patron has exactly one Schwab account, persist+return its hash.

    Common-case shortcut for the bootstrap path: single-account patrons
    skip the explicit get_account_numbers → update_patron_credential
    round-trip. Multi-account or zero-account patrons return None so
    _require_session can surface the standard ``account_hash_required``
    recipe and let the patron choose deliberately.

    Best-effort: a network failure or unexpected upstream shape returns
    None, falling back to the explicit-selection path.
    """
    access_token = creds.get("access_token", "")
    if not access_token:
        return None

    import httpx as _httpx
    settings = _get_settings()
    try:
        async with _httpx.AsyncClient() as http:
            resp = await http.get(
                f"{settings.schwab_trader_api}/trader/v1/accounts/accountNumbers",
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=10.0,
            )
            resp.raise_for_status()
            accounts = resp.json()
    except Exception as exc:
        logger.info("Auto-select account fetch failed for %s: %s", npub[:20], exc)
        return None

    if not isinstance(accounts, list) or len(accounts) != 1:
        # Zero or many — let the patron pick explicitly
        return None

    selected = accounts[0].get("hashValue", "")
    if not selected:
        return None

    # Persist via the wheel's update_patron_credential, which on v0.17.3+
    # routes to the OAuth service blob automatically when no patron
    # credential template is set. Best-effort — if persistence fails,
    # we still return the hash so this call succeeds; the next call
    # will simply re-auto-select.
    try:
        await runtime.update_patron_credential(npub, "account_hash", selected)
        logger.info(
            "Auto-selected sole Schwab account for %s and persisted account_hash.",
            npub[:20],
        )
    except Exception as exc:
        logger.warning("Auto-select persist failed (will retry next call): %s", exc)
    return selected


async def _require_session(npub: str):
    """Resolve a patron's Schwab session, refreshing tokens transparently.

    Always routes through ``runtime.restore_oauth_session`` which loads
    from vault, refreshes via the upstream provider if expired, and
    persists rotated tokens back to vault.  Eliminates the prior bug
    where in-memory token refresh was lost on process restart.

    Returns a ``UserSession`` on success, or a structured error dict
    (``{"success": False, "error_code": ..., "next_steps": [...]}``)
    on any non-success situation — never raises ValueError for routine
    refresh paths.
    """
    err = runtime.npub_validation_error(npub)
    if err is not None:
        return err

    # Always go through the wheel's restore-refresh-persist cycle.
    creds, situation = await runtime.restore_oauth_session(npub)
    if creds is None:
        return _resolution_for(situation)

    account_hash = creds.get("account_hash", "")
    if not account_hash:
        # Single-account patrons are the common case. Fetch the account
        # list and auto-select if there's exactly one — saves the agent
        # an entire round-trip through get_account_numbers + update_patron_credential.
        # Multi-account or zero-account patrons still get the explicit
        # account_hash_required recipe so they choose deliberately.
        auto = await _try_auto_select_account_hash(npub, creds)
        if auto is None:
            return _resolution_for("no_account_hash")
        account_hash = auto

    try:
        op_creds = await _ensure_operator_credentials()
    except Exception:
        return _resolution_for("operator_not_configured")

    settings = _get_settings()
    from vault import UserSession, _create_client

    # Wire a refresh-persist callback so any in-memory refresh
    # inside SchwabClient (race conditions, near-expiry windows)
    # also reaches the vault — belt-and-suspenders alongside the
    # primary restore_oauth_session path.
    async def _persist_refreshed(token_dict: dict[str, Any]) -> None:
        try:
            import json as _json
            import time as _time
            vault_data = {
                "token_json": _json.dumps(token_dict),
                "access_token": token_dict.get("access_token", ""),
                "refresh_token": token_dict.get("refresh_token", creds.get("refresh_token", "")),
                "expires_at": str(token_dict.get("expires_at", _time.time() + 1800)),
                "token_type": token_dict.get("token_type", "Bearer"),
                "account_hash": account_hash,
            }
            await runtime.store_patron_session(npub, vault_data, service="schwab")
            logger.info("In-memory Schwab refresh persisted to vault for %s.", npub[:20])
        except Exception as exc:
            logger.warning("Failed to persist in-memory Schwab refresh: %s", exc)

    client = _create_client(
        op_creds["client_id"],
        op_creds["client_secret"],
        creds["token_json"],
        api_base=settings.schwab_trader_api,
        on_token_refresh=_persist_refreshed,
    )
    return UserSession(
        token_json=creds["token_json"],
        account_hash=account_hash,
        client=client,
        npub=npub,
    )


# ---------------------------------------------------------------------------
# MCP Tools — Paid (Schwab brokerage data, domain-specific)
# OAuth tools (begin_oauth, check_oauth_status) are now standard
# wheel tools, registered via OAuthProviderConfig.
# ---------------------------------------------------------------------------


@tool
async def get_account_numbers(npub: NpubField = "", proof: str = "") -> str | dict[str, Any]:
    """List Schwab account numbers and their hash identifiers.

    Call after completing OAuth. Returns accounts with hash values
    needed for brokerage data tools. Then call
    ``update_patron_credential(field="account_hash", value=<hash>)``
    to set your preferred account. Free.

    Args:
        npub: Your DPYC patron Nostr public key (npub1...).
    """
    if not npub or not npub.startswith("npub1"):
        return {"success": False, "error": "npub is required."}

    # Need OAuth tokens but NOT account_hash
    creds, situation = await runtime.restore_oauth_session(npub)
    if creds is None:
        return _resolution_for(situation)

    access_token = creds.get("access_token", "")
    if not access_token:
        return _resolution_for("no_credentials")

    import httpx
    async with httpx.AsyncClient() as http:
        settings = _get_settings()
        resp = await http.get(
            f"{settings.schwab_trader_api}/trader/v1/accounts/accountNumbers",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        resp.raise_for_status()
        accounts = resp.json()

    if not accounts:
        return {"success": False, "error": "No accounts found for this Schwab user."}

    return {
        "success": True,
        "accounts": [
            {"account_number": a["accountNumber"], "account_hash": a["hashValue"]}
            for a in accounts
        ],
        "message": (
            "Call update_patron_credential(npub=<your_npub>, "
            'field="account_hash", value=<hash>) to set your '
            "preferred account for brokerage data tools."
        ),
    }


@tool
@runtime.paid_tool(capability_uuid("get_brokerage_positions"), catch_errors=True)
async def get_brokerage_positions(npub: NpubField = "", proof: str = "") -> str | dict[str, Any]:
    """Get positions for a Schwab account.
    Args:
        npub: Your DPYC patron Nostr public key (npub1...) for credit attribution.
    """
    session = await _require_session(npub)
    if isinstance(session, dict):
        return session
    from tools.account import get_positions as _get_positions

    return await _get_positions(session.client, session.account_hash)


@tool
@runtime.paid_tool(capability_uuid("get_brokerage_balances"), catch_errors=True)
async def get_brokerage_balances(npub: NpubField = "", proof: str = "") -> str | dict[str, Any]:
    """Get account balances for a Schwab account.
    Args:
        npub: Your DPYC patron Nostr public key (npub1...) for credit attribution.
    """
    session = await _require_session(npub)
    if isinstance(session, dict):
        return session
    from tools.account import get_account_balances as _get_account_balances

    return await _get_account_balances(session.client, session.account_hash)


@tool
@runtime.paid_tool(capability_uuid("get_stock_quote"), catch_errors=True)
async def get_stock_quote(
    symbols: str, npub: NpubField = "", proof: str = "",
) -> str | dict[str, Any]:
    """Get real-time quotes for one or more symbols.
    Args:
        symbols: Comma-separated ticker symbols (e.g. "AAPL,MSFT,TSLA").
        npub: Your DPYC patron Nostr public key (npub1...) for credit attribution.
    """
    session = await _require_session(npub)
    if isinstance(session, dict):
        return session
    from tools.market import get_quote as _get_quote

    return await _get_quote(session.client, symbols)


@tool
@runtime.paid_tool(capability_uuid("get_option_chain"), catch_errors=True)
async def get_option_chain(
    symbol: str,
    strike_count: int = 20,
    contract_type: str = "ALL",
    days_to_expiration: int = 21,
    npub: NpubField = "", proof: str = "",
) -> str | dict[str, Any]:
    """Get filtered option chain for spread evaluation.
    Args:
        symbol: Underlying ticker symbol.
        strike_count: Number of strikes around ATM to include.
        contract_type: "ALL", "CALL", or "PUT".
        days_to_expiration: Maximum days to expiration to include.
        npub: Your DPYC patron Nostr public key (npub1...) for credit attribution.
    """
    session = await _require_session(npub)
    if isinstance(session, dict):
        return session
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
    npub: NpubField = "", proof: str = "",
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
    session = await _require_session(npub)
    if isinstance(session, dict):
        return session
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
    npub: NpubField = "", proof: str = "",
) -> str | dict[str, Any]:
    """Get top movers for a market index.
    Args:
        index: Index symbol -- "$DJI", "$COMPX", or "$SPX".
        sort: "PERCENT_CHANGE_UP", "PERCENT_CHANGE_DOWN", or "VOLUME".
        frequency: 0 = all, 1 = 1-5%, 2 = 5-10%, 3 = 10-20%, 4 = 20%+.
        npub: Your DPYC patron Nostr public key (npub1...) for credit attribution.
    """
    session = await _require_session(npub)
    if isinstance(session, dict):
        return session
    from tools.market import get_movers as _get_movers

    return await _get_movers(session.client, index, sort, frequency)


@tool
@runtime.paid_tool(capability_uuid("get_market_hours"), catch_errors=True)
async def get_market_hours(
    markets: str = "equity,option",
    date: str = "",
    npub: NpubField = "", proof: str = "",
) -> str | dict[str, Any]:
    """Get market hours for equity, option, bond, future, or forex markets.

    Args:
        markets: Comma-separated: "equity", "option", "bond", "future", "forex".
        date: ISO date to check (e.g. "2026-03-15"). Defaults to today.
        npub: Your DPYC patron Nostr public key (npub1...) for credit attribution.
    """
    session = await _require_session(npub)
    if isinstance(session, dict):
        return session
    from tools.market import get_market_hours as _get_market_hours

    return await _get_market_hours(
        session.client, markets, date=date or None,
    )


@tool
@runtime.paid_tool(capability_uuid("search_instruments"), catch_errors=True)
async def search_instruments(
    symbol: str,
    projection: str = "symbol-search",
    npub: NpubField = "", proof: str = "",
) -> str | dict[str, Any]:
    """Search for instruments by symbol, name, or CUSIP.
    Args:
        symbol: Search term -- ticker, partial name, or CUSIP.
        projection: "symbol-search", "symbol-regex", "desc-search",
            "desc-regex", or "fundamental".
        npub: Your DPYC patron Nostr public key (npub1...) for credit attribution.
    """
    session = await _require_session(npub)
    if isinstance(session, dict):
        return session
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
    npub: NpubField = "", proof: str = "",
) -> str | dict[str, Any]:
    """Get order history for your Schwab account.
    Args:
        from_date: Start date (ISO 8601). Defaults to 30 days ago.
        to_date: End date (ISO 8601). Defaults to now.
        status_filter: Optional status filter (e.g. "FILLED", "CANCELED", "WORKING").
        npub: Your DPYC patron Nostr public key (npub1...) for credit attribution.
    """
    session = await _require_session(npub)
    if isinstance(session, dict):
        return session
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
async def get_brokerage_order(
    order_id: str, npub: NpubField = "", proof: str = "",
) -> str | dict[str, Any]:
    """Get details for a single order by ID.
    Args:
        order_id: The Schwab order ID.
        npub: Your DPYC patron Nostr public key (npub1...) for credit attribution.
    """
    session = await _require_session(npub)
    if isinstance(session, dict):
        return session
    from tools.account import get_order as _get_order

    return await _get_order(session.client, session.account_hash, order_id)


@tool
@runtime.paid_tool(capability_uuid("get_brokerage_transactions"), catch_errors=True)
async def get_brokerage_transactions(
    from_date: str = "",
    to_date: str = "",
    transaction_types: str = "",
    npub: NpubField = "", proof: str = "",
) -> str | dict[str, Any]:
    """Get transaction history for your Schwab account.
    Args:
        from_date: Start date (ISO 8601). Defaults to 30 days ago.
        to_date: End date (ISO 8601). Defaults to now.
        transaction_types: Comma-separated types: TRADE, DIVIDEND, CASH_IN_OR_CASH_OUT, etc.
        npub: Your DPYC patron Nostr public key (npub1...) for credit attribution.
    """
    session = await _require_session(npub)
    if isinstance(session, dict):
        return session
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
    transaction_id: str, npub: NpubField = "", proof: str = "",
) -> str | dict[str, Any]:
    """Get details for a single transaction by ID.
    Args:
        transaction_id: The Schwab transaction ID.
        npub: Your DPYC patron Nostr public key (npub1...) for credit attribution.
    """
    session = await _require_session(npub)
    if isinstance(session, dict):
        return session
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
