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
    to set your preferred account.

    Free (no api_sats deducted) but **proof-gated**: the caller must
    prove Schnorr-control of ``npub`` via ``request_npub_proof`` +
    ``receive_npub_proof`` first, then pass the resulting token here.
    Without the proof check, an attacker who knew a patron's public
    npub could fetch that patron's Schwab account hashes (IDOR).

    Args:
        npub: Your DPYC patron Nostr public key (npub1...).
        proof: Schnorr proof token issued by request/receive_npub_proof
            for capability ``get_account_numbers``.
    """
    err = runtime.npub_validation_error(npub)
    if err is not None:
        return err
    err = runtime.proof_validation_error(proof)
    if err is not None:
        return err
    from tollbooth.identity_proof import verify_proof
    if not verify_proof(proof, npub, "get_account_numbers"):
        return {
            "success": False,
            "error_code": "proof_invalid",
            "error": "Invalid or expired proof for npub. Re-run request_npub_proof + receive_npub_proof.",
        }

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
    """Get current positions in the active Schwab account, with automatic
    vertical-spread detection.

    Pulls Schwab's account endpoint with fields="positions" and emits up to
    three markdown sections, omitting any that are empty:

      ## Spreads — vertical spreads detected from paired option legs:
        - <underlying> <spread_type> (<short_strike>/<long_strike> P|C exp <date>,
          DTE <n>) | Credit: $X | Max Loss: $Y | Current: $Z | P&L: $W

      ## Options (unmatched) — single legs not paired into a spread:
        - <underlying> <strike> P|C exp <date> (DTE <n>) | Qty: ±N | Avg: $X |
          MktVal: $Y | P&L: $Z

      ## Equities — long/short share positions:
        - <symbol> | Qty: ±N | Avg: $X | Price: $Y | P&L: $Z

    Quantities are computed as (longQuantity − shortQuantity) — short positions
    show as negative numbers in Qty.

    Spread detection is heuristic: legs of the same underlying with matching
    expiration and put/call type, opposite long/short direction, and adjacent
    strikes get paired. Anything that doesn't fit cleanly drops into Options
    (unmatched). The tool does not currently detect iron condors, butterflies,
    or calendars — those will appear as multiple Options (unmatched) rows.

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
    """Get the active Schwab account's current balance summary.

    Pulls Schwab's account endpoint and returns four bold lines:

      **Cash Balance:** currentBalances.cashBalance
      **Buying Power:** currentBalances.buyingPower
      **Net Liquidation:** currentBalances.liquidationValue
      **Day P&L:** currentBalances.liquidationValue − initialBalances.liquidationValue

    Day P&L is the session change in mark-to-market equity (the canonical
    measure of "how much did I make/lose today"). Schwab's account
    response does not expose a single "dayProfitLoss" field — the
    convention is to compute the delta against the start-of-day snapshot.

    Two fallback guards apply to Day P&L:
      1. Missing snapshot — if either initialBalances or currentBalances
         is absent or has a zero liquidationValue, Day P&L reports 0.0
         rather than treating zero as the baseline (which would print
         today's full equity as P&L).
      2. Suspect snapshot — if the computed Day P&L is larger in
         absolute value than half of current liquidation value (e.g.
         $17,442 P&L on an $8,847 account), the initialBalances snapshot
         is treated as stale or partial and Day P&L reports 0.0. A
         legitimate 50%+ session change is implausible for any normal
         account; the tool underreports in the rare real-50% case rather
         than emitting nonsense in the more common stale-snapshot case.

    When Day P&L reads $0.00 on a session where you expect a real number,
    one of those two guards fired. Cross-check against position-level P&L
    via get_brokerage_positions.

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

    Returns one markdown line per symbol with these fields:
      - Last:  intraday last-trade price.
      - Bid / Ask:  current best quote.
      - Vol:  cumulative session volume.
      - Chg:  Schwab's netPercentChange — session percent change vs prior close
              (not a tick-by-tick delta).
      - 52wk:  52-week low / 52-week high reference range.

    Symbology conventions (Schwab API — quietly enforced):
      - Equities and ETFs use bare tickers: AAPL, MSFT, XOM, GDX.
      - Indices require a $-prefix: $SPX (S&P 500), $DJI (Dow), $COMPX (Nasdaq
        Composite), $VIX (CBOE Volatility Index). The .X suffix (e.g. SPX.X) is
        NOT supported and will return an empty quote.
      - Mixing styles in a single call is fine: "AAPL,$SPX,$VIX".

    Args:
        symbols: Comma-separated ticker symbols (e.g. "AAPL,MSFT,$SPX").
            Each symbol is uppercased before lookup; whitespace around commas
            is tolerated. Symbols Schwab cannot resolve are silently omitted.
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
    """Get a filtered option chain suitable for spread evaluation.

    Returns a markdown table of surviving contracts with one row per leg.
    Header line carries the underlying price and the active filter constants.

    Columns:
      Exp | DTE | P/C | Strike | OTM% | Bid | Ask | Last | Vol | OI | IV | Delta | Theta

    ATM strikes (within 1% of the underlying) are marked with a trailing "*"
    in the Strike column. Rows are sorted by (expiration, put/call, strike).

    Server-side filters applied BEFORE the table is built — strikes failing
    a filter are silently dropped (not flagged as missing):
      - Open interest: hardcoded at OI >= 25 per contract. Zero-OI strikes
        and any below the threshold are excluded. This is NOT a parameter;
        the constant lives in tools/options.py.
      - Days to expiration: ceiling enforced via the days_to_expiration
        argument. Expirations beyond that horizon are excluded.

    Parameter semantics worth knowing:
      - strike_count: passed to Schwab as strikeCount. Schwab returns approximately
        this many strikes centered around the at-the-money strike (so 20 means
        roughly 10 below + 10 above ATM; exact centering is Schwab's call).
        After the OI filter, the visible count is typically lower.
      - contract_type: "ALL" returns both legs; "CALL" or "PUT" returns only
        that side.

    Failure modes worth distinguishing:
      - "No option contracts found ... within K DTE with OI >= 25" — the chain
        exists but every strike in the requested window failed the OI filter.
        Bump strike_count first (widens the strike band), then days_to_expiration
        (extends the horizon).
      - An error response — the underlying symbol failed to resolve.

    Strike-grid quirk worth knowing — interaction with the OI filter:
      On high-priced underlyings (~$300+), $2.50-increment strikes often
      exist on Schwab's underlying grid but carry OI below 25 in OTM
      territory and get filtered out — leaving the VISIBLE chain at $5
      increments with an occasional $2.50 outlier near ATM. Example: ISRG
      around $420 typically shows $5 strikes; CRM around $177 shows $2.50
      strikes everywhere. This is the OI filter interacting with market
      microstructure, not "the underlying doesn't have $2.50 strikes."
      The $2.50 grid is more reliably populated on underlyings in the
      $50-$250 range. If you need a finer grid on an expensive underlying,
      that's a sign to lower the OI floor, which currently requires editing
      tools/options.py rather than passing a parameter.

    Args:
        symbol: Underlying ticker (equity or ETF). For index options use the
            $-prefix form: $SPX, $NDX, $RUT.
        strike_count: Approximate total strikes returned, centered on ATM
            (default 20).
        contract_type: "ALL", "CALL", or "PUT".
        days_to_expiration: Maximum days to expiration to include (default 21).
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
    """Get historical OHLCV candle data for a symbol.

    Returns a markdown table of the most recent candles within the requested
    period, capped at the last 30 rows for readability. A footnote line is
    added when truncation occurs so the agent knows more data was available.

    Columns:
      Date | Open | High | Low | Close | Volume

    Truncation rule (hardcoded in tools/market.py):
      - The Schwab response may contain hundreds of candles; this tool
        slices to the most recent 30 before formatting. The number of
        candles Schwab actually returns is driven by Schwab's defaults for
        the given (period_type, period, frequency_type, frequency) tuple,
        not by a per-call parameter on this tool.

    Schwab's valid combinations (from Schwab's price-history API):
      - period_type "day": period in {1,2,3,4,5,10}; frequency_type "minute"
        only; frequency in {1,5,10,15,30}.
      - period_type "month": period in {1,2,3,6}; frequency_type in
        {"daily","weekly"}.
      - period_type "year": period in {1,2,3,5,10,15,20}; frequency_type in
        {"daily","weekly","monthly"}.
      - period_type "ytd": period in {1}; frequency_type in
        {"daily","weekly"}.

    Args:
        symbol: Ticker symbol (equity, ETF, or $-prefixed index).
        period_type: "day", "month", "year", or "ytd".
        period: Number of periods (see valid combinations above).
        frequency_type: "minute", "daily", "weekly", or "monthly".
        frequency: Frequency interval (only meaningful for "minute" candles).
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
    """Get top movers for a market index — Schwab's curated mover screener.

    Returns up to 20 rows (capped server-side here, not by Schwab) in a
    markdown table.

    Columns:
      Symbol | Description | Change % | Volume | Last

    Behavior worth knowing before reading the result:
      - The Change % column is a SHORT-WINDOW TICK-LEVEL DELTA from
        Schwab's mover feed — NOT session percent change vs prior close.
        Observed values are typically tiny (e.g. NVDA +0.02%) even on a
        day when the underlying has moved a full percent. For session %,
        call get_stock_quote on the symbol — that's the netPercentChange
        field, which is the canonical "how much did it move today" number.
      - The Volume column carries Schwab's AGGREGATE INDEX VOLUME — the same
        value appears in every row, not per-symbol volume. To get a symbol's
        own volume, call get_stock_quote on that symbol.
      - The symbol list is curated by Schwab's mover-detection algorithm, not
        a simple top-N sort of the index's constituents. Symbols not flagged
        as movers will be absent regardless of their actual change%, and you
        cannot reproduce the list by sorting the whole index yourself.
      - The sort parameter is a HINT to Schwab's mover algorithm about which
        direction of movement to prioritize surfacing. It does NOT guarantee
        directional filtering: a sort=PERCENT_CHANGE_DOWN call may include
        symbols moving up if Schwab's mover detection still flags them as
        relevant. Treat row order as Schwab's recommendation, not a sort key,
        and don't assume direction.

    Args:
        index: Index symbol. Schwab's movers endpoint supports only "$SPX",
            "$DJI", and "$COMPX". Other indices ($VIX, $NDX, $RUT, sector
            ETFs) are not supported and will return an empty list.
        sort: "PERCENT_CHANGE_UP", "PERCENT_CHANGE_DOWN", or "VOLUME".
        frequency: Movement-magnitude band filter.
            0 = all bands, 1 = 1–5%, 2 = 5–10%, 3 = 10–20%, 4 = 20%+.
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
    """Get trading hours for one or more market types.

    Returns nested markdown — one block per market product Schwab knows
    about within the requested categories:

      **<Product Name>** — OPEN | CLOSED
        Pre Market:  YYYY-MM-DDTHH:MM — YYYY-MM-DDTHH:MM
        Regular Market: YYYY-MM-DDTHH:MM — YYYY-MM-DDTHH:MM
        Post Market: YYYY-MM-DDTHH:MM — YYYY-MM-DDTHH:MM

    Sessions are emitted only when Schwab reports hours for them — a closed
    market on a weekend or holiday will have no session lines under it.

    Args:
        markets: Comma-separated market types. Schwab supports "equity",
            "option", "bond", "future", "forex". Unknown types are silently
            dropped by Schwab.
        date: ISO date to check (e.g. "2026-03-15"). Defaults to today when
            empty. The response is for a single trading day — pass each date
            explicitly if you need a multi-day forecast.
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
    """Search Schwab's instrument catalog by symbol, name, or CUSIP.

    Returns up to 25 results in a markdown list (capped server-side here;
    Schwab itself may return more). A truncation footnote appears when the
    full result set exceeded 25.

    Each row carries: symbol, asset type, description, optional exchange,
    optional CUSIP, and — when projection="fundamental" — P/E, dividend
    yield, and market cap in $B or $M.

      - **<SYM>** (<ASSET_TYPE>) — <description> [<EXCHANGE>] CUSIP:<CUSIP>
        | P/E:N.N | Yield:N.NN% | MktCap:$XB

    Projection options (Schwab's API enum — determines how the search term
    is interpreted, not just what fields come back):
      - symbol-search:  exact match on symbol (default; cheapest call).
      - symbol-regex:   regex match against symbols. The pattern is regex,
                        not a glob — "AAP.*" matches AAPL, AAP, etc.
      - desc-search:    full-text match against the instrument description
                        ("Apple", "semiconductor").
      - desc-regex:     regex against descriptions.
      - fundamental:    fetch fundamentals (P/E, yield, market cap) for a
                        specific symbol. Use this when you already know the
                        ticker and want the numbers, not a search.

    Args:
        symbol: Search term — ticker, regex, partial name, or CUSIP. The
            interpretation depends on `projection`.
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
    """Get order history for the active Schwab account.

    Returns one markdown row per order:

      - **<orderId>** [<status>] <orderType> | <leg1> / <leg2> / ... |
        Price: $X @ $avg_fill | Filled: <qty> | <enteredTime>

    Each leg formats as "<instruction> <quantity>x <symbol>" (e.g.
    "BUY 1x AAPL", "SELL_TO_OPEN 5x AAPL  240315C00185000"). The avg_fill
    suffix is the average across all executionLegs.price values for the
    order; omitted if the order has no fills yet.

    Date-window default — when from_date and to_date are both blank, the
    tool defaults to the last 30 days (in UTC). Pass either parameter to
    override; if you pass one, pass both.

    Schwab's order status enum (values you can pass to status_filter):
      AWAITING_PARENT_ORDER, AWAITING_CONDITION, AWAITING_STOP_CONDITION,
      AWAITING_MANUAL_REVIEW, ACCEPTED, AWAITING_UR_OUT, PENDING_ACTIVATION,
      QUEUED, WORKING, REJECTED, PENDING_CANCEL, CANCELED, PENDING_REPLACE,
      REPLACED, FILLED, EXPIRED, NEW.

    Args:
        from_date: Start of window, ISO 8601 (e.g. "2026-04-01T00:00:00.000Z").
            Empty string defaults to 30 days ago.
        to_date: End of window, ISO 8601. Empty string defaults to now.
        status_filter: Optional single Schwab status value (e.g. "FILLED",
            "CANCELED", "WORKING"). Empty string = all statuses.
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
    """Get full details for a single order by Schwab order ID.

    Returns the same one-line markdown format as get_brokerage_orders, with
    the average fill price computed across all executionLegs:

      - **<orderId>** [<status>] <orderType> | <legs> | Price: $X @ $avg_fill |
        Filled: <qty> | <enteredTime>

    Use this when you already have an orderId (e.g., from
    get_brokerage_orders or from a fill notification) and want a single
    crisp row rather than the full history list.

    Args:
        order_id: The Schwab order ID as returned by get_brokerage_orders.
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
    """Get transaction history for the active Schwab account.

    Returns one markdown row per transaction:

      - **<activityId>** [<type>] <tradeDate> | <qty>x <symbol> | <qty>x <symbol> ... |
        Net: $<amount>

    Symbols come from the transaction's transferItems collection (one item
    per leg, e.g. equity bought + cash debit), with the per-leg amount as
    quantity. When no transferItems have symbols, the row falls back to the
    transaction's description text in place of the symbol list.

    Date-window default — when from_date and to_date are both blank, the
    tool defaults to the last 30 days (in UTC). Pass both or neither.

    Schwab's transaction type enum (values you can pass to transaction_types):
      TRADE, RECEIVE_AND_DELIVER, DIVIDEND_OR_INTEREST, ACH_RECEIPT,
      ACH_DISBURSEMENT, CASH_RECEIPT, CASH_DISBURSEMENT, ELECTRONIC_FUND,
      WIRE_OUT, WIRE_IN, JOURNAL, MEMORANDUM, MARGIN_CALL, MONEY_MARKET,
      SMA_ADJUSTMENT. Empty string = all types.

    Args:
        from_date: Start of window, ISO 8601 (e.g. "2026-04-01T00:00:00.000Z").
            Empty string defaults to 30 days ago.
        to_date: End of window, ISO 8601. Empty string defaults to now.
        transaction_types: Comma-separated Schwab transaction-type values.
            Empty string = all types.
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
    """Get full details for a single transaction by Schwab transaction ID.

    Returns the same one-line markdown format as get_brokerage_transactions:

      - **<activityId>** [<type>] <tradeDate> | <symbols/qtys> | Net: $<amount>

    Use this when you have a specific transactionId (from
    get_brokerage_transactions, a journal entry, or a confirmation) and want
    the canonical row rather than scanning a history window.

    Args:
        transaction_id: The Schwab transaction ID as returned by
            get_brokerage_transactions (usually surfaced as `activityId`).
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
