"""Schwab MCP Server — multi-tenant brokerage data for Claude.ai.

Tollbooth-monetized, DPYC-native. Each user delivers their own Schwab
OAuth token + account hash via Secure Courier; per-user AsyncClient
instances are cached in memory. All brokerage tools are credit-gated
via the full Tollbooth DPYC monetization stack (Lightning micropayments).
"""

from __future__ import annotations

import logging
from typing import Any

from fastmcp import FastMCP
from tollbooth.constants import ToolTier
from tollbooth.slug_tools import make_slug_tool

logger = logging.getLogger(__name__)

mcp = FastMCP(
    "Schwab MCP",
    instructions=(
        "Schwab MCP — AI agent access to Charles Schwab brokerage data, "
        "monetized via DPYC Tollbooth Lightning micropayments.\n\n"
        "## Getting Started\n\n"
        "1. Call `session_status` to check your current session.\n"
        "2. If no active session, follow the Secure Courier onboarding flow:\n"
        "   - Get your **patron npub** from the dpyc-oracle's how_to_join() tool — "
        "this is the npub you registered as a DPYC Citizen, your identity for credit operations\n"
        "   - Call `request_credential_channel(recipient_npub=<patron_npub>)` "
        "to receive a welcome DM\n"
        "   - Reply via your Nostr client with your Schwab credentials in JSON\n"
        "   - Call `receive_credentials(sender_npub=<patron_npub>)` to vault your credentials\n\n"
        "## Credits Model\n\n"
        "Tool calls cost api_sats per call. Auth and balance tools are always free. "
        "Use `check_balance` to see your balance. Top up via `purchase_credits`."
    ),
)
tool = make_slug_tool(mcp, "schwab")

_ONBOARDING_NEXT_STEPS = {
    "action": "secure_courier_onboarding",
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
        "the JSON format shown. Credentials must NEVER appear in this chat."
    ),
    "step_4": (
        "Once the user confirms they replied, call "
        "receive_credentials(sender_npub=<npub>) to vault the "
        "credentials for future sessions."
    ),
}

# ---------------------------------------------------------------------------
# Tool cost table
# ---------------------------------------------------------------------------

TOOL_COSTS: dict[str, int] = {
    # Free
    "session_status": ToolTier.FREE,
    "request_credential_channel": ToolTier.FREE,
    "receive_credentials": ToolTier.FREE,
    "forget_credentials": ToolTier.FREE,
    "check_balance": ToolTier.FREE,
    "purchase_credits": ToolTier.FREE,
    "check_payment": ToolTier.FREE,
    # Paid — READ tier (5 api_sats)
    "get_positions": ToolTier.WRITE,
    "get_balances": ToolTier.WRITE,
    "get_quote": ToolTier.WRITE,
    # Paid — HEAVY tier (10 api_sats)
    "get_option_chain": ToolTier.HEAVY,
    "get_price_history": ToolTier.HEAVY,
}


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
# DPYC registry resolution
# ---------------------------------------------------------------------------

_cached_operator_npub: str | None = None
_cached_authority_npub: str | None = None
_cached_authority_service_url: str | None = None


def _get_operator_npub() -> str:
    """Derive and cache the operator's npub from its NSEC."""
    global _cached_operator_npub
    if _cached_operator_npub is not None:
        return _cached_operator_npub

    from pynostr.key import PrivateKey  # type: ignore[import-untyped]

    settings = _get_settings()
    nsec = settings.tollbooth_nostr_operator_nsec
    if not nsec:
        raise RuntimeError(
            "Operator misconfigured: TOLLBOOTH_NOSTR_OPERATOR_NSEC not set. "
            "Cannot derive operator identity for registry lookup."
        )

    pk = PrivateKey.from_nsec(nsec)
    _cached_operator_npub = pk.public_key.bech32()
    return _cached_operator_npub


async def _resolve_authority_npub() -> str:
    """Look up upstream authority npub from DPYC registry. Cached for process lifetime."""
    global _cached_authority_npub
    if _cached_authority_npub is not None:
        return _cached_authority_npub

    from tollbooth.registry import DEFAULT_REGISTRY_URL, DPYCRegistry, RegistryError

    operator_npub = _get_operator_npub()
    settings = _get_settings()

    registry = DPYCRegistry(
        url=DEFAULT_REGISTRY_URL,
        cache_ttl_seconds=settings.dpyc_registry_cache_ttl_seconds,
    )
    try:
        authority_npub = await registry.resolve_authority_npub(operator_npub)
    except RegistryError as e:
        raise RuntimeError(
            f"Failed to resolve authority npub for operator {operator_npub}: {e}"
        ) from e
    finally:
        await registry.close()

    _cached_authority_npub = authority_npub
    logger.info(
        "Resolved authority npub: operator=%s authority=%s",
        operator_npub, authority_npub,
    )
    return authority_npub


async def _resolve_authority_service_url() -> str:
    """Resolve the Authority's MCP service URL from the DPYC community registry."""
    global _cached_authority_service_url
    if _cached_authority_service_url is not None:
        return _cached_authority_service_url

    from tollbooth.registry import DEFAULT_REGISTRY_URL, DPYCRegistry, RegistryError

    operator_npub = _get_operator_npub()
    settings = _get_settings()

    registry = DPYCRegistry(
        url=DEFAULT_REGISTRY_URL,
        cache_ttl_seconds=settings.dpyc_registry_cache_ttl_seconds,
    )
    try:
        svc = await registry.resolve_authority_service(operator_npub)
    except RegistryError as e:
        raise RuntimeError(
            f"Failed to resolve authority service for operator {operator_npub}: {e}"
        ) from e
    finally:
        await registry.close()

    _cached_authority_service_url = svc["url"]
    logger.info("Resolved authority service URL: %s", svc["url"])
    return _cached_authority_service_url


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


def _get_effective_user_id() -> str:
    """Return the npub for the current user. Required for credit operations."""
    from vault import get_dpyc_npub

    horizon_id = _get_current_user_id()
    if not horizon_id:
        return "stdio:0"

    npub = get_dpyc_npub(horizon_id)
    if not npub:
        raise ValueError(
            "No DPYC identity active. Credit operations require an npub. "
            "Call receive_credentials to complete the Secure Courier onboarding flow. "
            "Credentials must NEVER appear in this chat."
        )
    return npub


async def _ensure_dpyc_session() -> str:
    """Return the npub for the current user, auto-restoring on cold start."""
    horizon_id = _get_current_user_id()
    if not horizon_id:
        return "stdio:0"

    try:
        courier = _get_courier_service()
        return await courier.ensure_identity(horizon_id, service="schwab")
    except ValueError:
        raise
    except Exception:
        pass

    return _get_effective_user_id()


# ---------------------------------------------------------------------------
# Secure Courier singleton
# ---------------------------------------------------------------------------

_courier_service = None

_DEFAULT_RELAY = "wss://nostr.wine"
_FALLBACK_POOL = [
    "wss://relay.primal.net",
    "wss://relay.damus.io",
    "wss://nos.lol",
    "wss://relay.nostr.band",
]


def _resolve_relays(configured: str | None) -> list[str]:
    """Resolve relay list: env var -> default -> probe fallback pool."""
    from tollbooth.nostr_diagnostics import probe_relay_liveness

    if configured:
        relays = [r.strip() for r in configured.split(",") if r.strip()]
    else:
        relays = [_DEFAULT_RELAY]

    results = probe_relay_liveness(relays, timeout=5)
    live = [r["relay"] for r in results if r["connected"]]

    if live:
        logger.info("Relay probe: %d/%d configured relays live", len(live), len(relays))
        return live

    logger.warning("All configured relays down (%s), probing fallback pool...", ", ".join(relays))
    fallback_results = probe_relay_liveness(_FALLBACK_POOL, timeout=5)
    fallback_live = [r["relay"] for r in fallback_results if r["connected"]]

    if fallback_live:
        logger.info("Fallback relays live: %s", ", ".join(fallback_live))
        return fallback_live

    logger.warning("No relays responded -- using full list, hoping for recovery")
    return relays + _FALLBACK_POOL


async def _on_schwab_credentials_received(
    sender_npub: str, credentials: dict[str, str], service: str,
) -> dict[str, Any] | None:
    """Operator callback: activate session after credential receipt via Secure Courier.

    Combines the operator's client_id/secret with the patron's token_json + account_hash,
    creates an AsyncClient, establishes the in-memory session, and seeds the starter balance.
    """
    result: dict[str, Any] = {}

    user_id = _get_current_user_id()
    if not user_id:
        return result

    if not all(k in credentials for k in ("token_json", "account_hash")):
        return result

    settings = _get_settings()
    if not settings.schwab_client_id or not settings.schwab_client_secret:
        result["session_activated"] = False
        result["warning"] = (
            "Credentials received but operator SCHWAB_CLIENT_ID/SCHWAB_CLIENT_SECRET "
            "not configured. Session not activated."
        )
        return result

    from vault import _create_client_from_token, set_session

    client = _create_client_from_token(
        settings.schwab_client_id,
        settings.schwab_client_secret,
        credentials["token_json"],
    )

    set_session(
        user_id,
        credentials["token_json"],
        credentials["account_hash"],
        client,
        npub=sender_npub,
    )
    result["session_activated"] = True
    result["dpyc_npub"] = sender_npub

    seed_applied = await _seed_balance(sender_npub)
    if seed_applied:
        result["seed_applied"] = True
        result["seed_balance_api_sats"] = settings.seed_balance_sats

    return result


def _get_courier_service():
    """Get or create the SecureCourierService singleton."""
    global _courier_service
    if _courier_service is not None:
        return _courier_service

    from tollbooth.credential_templates import CredentialTemplate, FieldSpec
    from tollbooth.nostr_credentials import NostrProfile
    from tollbooth.secure_courier import SecureCourierService

    settings = _get_settings()

    nsec = settings.tollbooth_nostr_operator_nsec
    if not nsec:
        raise ValueError(
            "Secure Courier not configured. "
            "Set TOLLBOOTH_NOSTR_OPERATOR_NSEC to enable credential delivery via Nostr DM."
        )

    relays = _resolve_relays(settings.tollbooth_nostr_relays)

    templates = {
        "schwab": CredentialTemplate(
            service="schwab",
            version=1,
            fields={
                "token_json": FieldSpec(required=True, sensitive=True),
                "account_hash": FieldSpec(required=True, sensitive=True),
            },
            description="Schwab OAuth token JSON and account hash",
        ),
    }

    from tollbooth.vaults import NeonCredentialVault

    commerce_vault = _get_commerce_vault()
    credential_vault = NeonCredentialVault(neon_vault=commerce_vault)

    import asyncio
    try:
        asyncio.ensure_future(credential_vault.ensure_schema())
    except RuntimeError:
        pass

    _courier_service = SecureCourierService(
        operator_nsec=nsec,
        relays=relays,
        templates=templates,
        credential_vault=credential_vault,
        profile=NostrProfile(
            name="schwab-mcp",
            display_name="Schwab MCP",
            about=(
                "Read-only Schwab brokerage data — Tollbooth DPYC monetized, Nostr-native. "
                "Send credentials via encrypted DM (Secure Courier)."
            ),
            website="https://github.com/lonniev/schwab-mcp",
        ),
        on_credentials_received=_on_schwab_credentials_received,
    )

    return _courier_service


# ---------------------------------------------------------------------------
# Commerce vault + LedgerCache + BTCPay singletons
# ---------------------------------------------------------------------------

_commerce_vault = None
_ledger_cache = None
_btcpay_client = None


def _get_commerce_vault():
    """Singleton commerce vault for ledger persistence (NeonVault)."""
    global _commerce_vault
    if _commerce_vault is not None:
        return _commerce_vault

    settings = _get_settings()

    if settings.neon_database_url:
        from tollbooth.vaults import NeonVault

        vault = NeonVault(database_url=settings.neon_database_url)
        import asyncio

        try:
            asyncio.ensure_future(vault.ensure_schema())
        except RuntimeError:
            pass
        logger.info("NeonVault initialized for ledger persistence.")
    else:
        raise ValueError(
            "Commerce vault not configured. Set NEON_DATABASE_URL to enable credits."
        )

    _commerce_vault = vault
    return _commerce_vault


def _get_ledger_cache():
    """Get or create the LedgerCache singleton."""
    global _ledger_cache
    if _ledger_cache is not None:
        return _ledger_cache

    from tollbooth.ledger_cache import LedgerCache

    vault = _get_commerce_vault()
    _ledger_cache = LedgerCache(vault)

    import asyncio

    try:
        asyncio.ensure_future(_ledger_cache.start_background_flush())
    except RuntimeError:
        pass

    return _ledger_cache


def _get_btcpay():
    """Get or create the BTCPayClient singleton."""
    global _btcpay_client
    if _btcpay_client is not None:
        return _btcpay_client

    from tollbooth.btcpay_client import BTCPayClient

    settings = _get_settings()
    if not settings.btcpay_host or not settings.btcpay_store_id or not settings.btcpay_api_key:
        raise ValueError(
            "BTCPay not configured. Set BTCPAY_HOST, BTCPAY_STORE_ID, BTCPAY_API_KEY."
        )

    _btcpay_client = BTCPayClient(
        host=settings.btcpay_host,
        api_key=settings.btcpay_api_key,
        store_id=settings.btcpay_store_id,
    )
    return _btcpay_client


# ---------------------------------------------------------------------------
# Session resolution helpers
# ---------------------------------------------------------------------------


def _require_session(user_id: str):
    """Get per-user session or raise ValueError."""
    from vault import get_session

    session = get_session(user_id)
    if session is None:
        raise ValueError(
            "No active Schwab session. Use receive_credentials to deliver your "
            "Schwab token via Secure Courier."
        )
    return session


# ---------------------------------------------------------------------------
# Credit gating helpers
# ---------------------------------------------------------------------------


async def _debit_or_error(tool_name: str) -> dict[str, Any] | None:
    """Check balance and debit credits for a paid tool call.

    Returns None to proceed, or an error dict to short-circuit.
    """
    cost = TOOL_COSTS.get(tool_name, 0)
    if cost == 0:
        return None

    try:
        user_id = await _ensure_dpyc_session()
    except ValueError as e:
        return {"success": False, "error": str(e)}

    try:
        cache = _get_ledger_cache()
    except Exception as e:
        return {
            "success": False,
            "error": (
                f"Credit system unavailable: {e}. "
                "The operator must configure NEON_DATABASE_URL to enable credits."
            ),
        }

    if not await cache.debit(user_id, tool_name, cost):
        try:
            ledger = await cache.get(user_id)
            bal = ledger.balance_api_sats
        except Exception:
            bal = 0
        return {
            "success": False,
            "error": (
                f"Insufficient balance ({bal} api_sats) "
                f"for {tool_name} ({cost} api_sats). "
                f"Use purchase_credits to add funds."
            ),
        }

    return None


async def _rollback_debit(tool_name: str) -> None:
    """Undo a debit when the downstream API call fails."""
    cost = TOOL_COSTS.get(tool_name, 0)
    if cost == 0:
        return

    try:
        user_id = await _ensure_dpyc_session()
        cache = _get_ledger_cache()
        ledger = await cache.get(user_id)
    except Exception:
        return

    ledger.rollback_debit(tool_name, cost)
    cache.mark_dirty(user_id)


async def _with_warning(result: dict[str, Any]) -> dict[str, Any]:
    """Attach a low-balance warning to a paid tool result if balance is low."""
    try:
        from tollbooth.tools.credits import compute_low_balance_warning

        user_id = await _ensure_dpyc_session()
        cache = _get_ledger_cache()
        ledger = await cache.get(user_id)
        settings = _get_settings()
        warning = compute_low_balance_warning(ledger, settings.seed_balance_sats)
        if warning:
            result = dict(result)
            result["low_balance_warning"] = warning
    except Exception:
        pass
    return result


async def _seed_balance(npub: str) -> bool:
    """Apply seed balance for a new user (idempotent via sentinel)."""
    settings = _get_settings()
    if settings.seed_balance_sats <= 0:
        return False
    try:
        cache = _get_ledger_cache()
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
# MCP Tools — Free
# ---------------------------------------------------------------------------


@tool
async def session_status() -> dict[str, Any]:
    """Check the status of your current session.

    Shows whether you have an active Schwab session, DPYC identity state,
    and next steps for onboarding if needed.
    """
    from vault import get_dpyc_npub, get_session

    user_id = _get_current_user_id()
    if not user_id:
        return {
            "mode": "stdio",
            "message": "Running in STDIO mode (local dev).",
            "personal_session": False,
        }

    session = get_session(user_id)
    if session:
        result: dict[str, Any] = {
            "mode": "cloud",
            "personal_session": True,
            "session_age_seconds": session.age_seconds,
            "message": "Personal Schwab credentials active.",
        }
        npub = get_dpyc_npub(user_id)
        if npub:
            result["dpyc_npub"] = npub
        else:
            result["dpyc_warning"] = "No DPYC identity active."
        return result

    return {
        "mode": "cloud",
        "personal_session": False,
        "message": (
            "No active session. Follow the next_steps to onboard via "
            "Secure Courier -- credentials travel via encrypted Nostr DM "
            "and never appear in this chat."
        ),
        "next_steps": _ONBOARDING_NEXT_STEPS,
    }


# ---------------------------------------------------------------------------
# MCP Tools — Secure Courier (Free)
# ---------------------------------------------------------------------------


@tool
async def request_credential_channel(
    service: str = "schwab",
    recipient_npub: str | None = None,
) -> dict[str, Any]:
    """Open a Secure Courier channel for out-of-band credential delivery.

    If you provide your npub, the service sends you a welcome DM -- just
    open your Nostr client and reply to it with your credentials.

    How it works:
    1. Call this tool with your npub -- a welcome DM arrives in your Nostr inbox.
    2. Open your Nostr client (Primal, Damus, Amethyst, etc.).
    3. Reply with JSON: {"token_json": "...", "account_hash": "..."}.
    4. Return here and call receive_credentials with your npub.

    Your credentials never appear in this chat.

    Args:
        service: Which credential template to use (default "schwab").
        recipient_npub: Your **patron** Nostr public key (npub1...).
    """
    try:
        courier = _get_courier_service()
    except (ValueError, RuntimeError) as e:
        return {"success": False, "error": str(e)}

    try:
        return await courier.open_channel(
            service,
            greeting=(
                "Hi -- I'm Schwab MCP, a Tollbooth service for read-only "
                "Schwab brokerage data. You (or your AI agent) requested a "
                "credential channel."
            ),
            recipient_npub=recipient_npub,
        )
    except Exception as e:
        return {"success": False, "error": str(e)}


@tool
async def receive_credentials(
    sender_npub: str,
    service: str = "schwab",
) -> dict[str, Any]:
    """Pick up credentials delivered via the Secure Courier.

    If you've previously delivered credentials, they'll be returned
    from the encrypted vault without any relay I/O.

    Credential values are NEVER echoed back -- only the field count and
    service name are returned.

    Args:
        sender_npub: Your **patron** Nostr public key (npub1...).
        service: Which credential template to match (default "schwab").
    """
    try:
        courier = _get_courier_service()
    except (ValueError, RuntimeError) as e:
        return {"success": False, "error": str(e)}

    try:
        return await courier.receive(
            sender_npub, service=service, caller_id=_get_current_user_id(),
        )
    except Exception as e:
        return {"success": False, "error": str(e)}


@tool
async def forget_credentials(sender_npub: str, service: str = "schwab") -> dict[str, Any]:
    """Delete vaulted credentials so you can re-deliver via Secure Courier.

    Use this when you've rotated your Schwab token and need to send fresh
    credentials through the diplomatic pouch.

    Args:
        sender_npub: Your Nostr public key (npub1...).
        service: Which service's credentials to forget (default "schwab").
    """
    try:
        courier = _get_courier_service()
    except (ValueError, RuntimeError) as e:
        return {"success": False, "error": str(e)}

    return await courier.forget(
        sender_npub, service=service, caller_id=_get_current_user_id(),
    )


# ---------------------------------------------------------------------------
# MCP Tools — Credit Management (Free)
# ---------------------------------------------------------------------------


@tool
async def purchase_credits(amount_sats: int) -> dict[str, Any]:
    """Create a BTCPay Lightning invoice to purchase credits for tool calls.

    Call flow:
    1. Call purchase_credits(amount_sats) -> get Lightning invoice
    2. Pay the invoice with any Lightning wallet
    3. Call check_payment(invoice_id) -> credits land in your balance

    Args:
        amount_sats: Number of satoshis to purchase (minimum 1, maximum 1,000,000).
    """
    from tollbooth.tools import credits

    try:
        user_id = await _ensure_dpyc_session()
        btcpay = _get_btcpay()
        cache = _get_ledger_cache()
    except ValueError as e:
        return {"success": False, "error": str(e)}

    settings = _get_settings()
    try:
        authority_npub = await _resolve_authority_npub()
        authority_url = await _resolve_authority_service_url()
        operator_npub = _get_operator_npub()
    except RuntimeError as e:
        return {"success": False, "error": str(e)}

    from tollbooth.authority_client import AuthorityCertifier, AuthorityCertifyError

    certifier = AuthorityCertifier(authority_url, operator_npub)
    try:
        cert_result = await certifier.certify(amount_sats)
    except AuthorityCertifyError as e:
        return {"success": False, "error": f"Authority certification failed: {e}"}

    return await credits.purchase_credits_tool(
        btcpay, cache, user_id, amount_sats,
        certificate=cert_result["certificate"],
        authority_npub=authority_npub,
        tier_config_json=settings.btcpay_tier_config,
        user_tiers_json=settings.btcpay_user_tiers,
        default_credit_ttl_seconds=settings.credit_ttl_seconds,
    )


@tool
async def check_payment(invoice_id: str) -> dict[str, Any]:
    """Verify that a Lightning invoice has settled and credit the payment to your balance.

    Safe to call multiple times -- credits are only granted once per invoice.

    Args:
        invoice_id: The BTCPay invoice ID returned by purchase_credits.
    """
    from tollbooth.tools import credits

    try:
        user_id = await _ensure_dpyc_session()
        btcpay = _get_btcpay()
        cache = _get_ledger_cache()
    except ValueError as e:
        return {"success": False, "error": str(e)}

    settings = _get_settings()
    return await credits.check_payment_tool(
        btcpay, cache, user_id, invoice_id,
        tier_config_json=settings.btcpay_tier_config,
        user_tiers_json=settings.btcpay_user_tiers,
        default_credit_ttl_seconds=settings.credit_ttl_seconds,
    )


@tool
async def check_balance() -> dict[str, Any]:
    """Check your current credit balance, tier info, and usage summary.

    Read-only -- no side effects. Call anytime to check funding level.
    """
    from tollbooth.tools import credits

    try:
        user_id = await _ensure_dpyc_session()
        cache = _get_ledger_cache()
    except ValueError as e:
        return {"success": False, "error": str(e)}

    settings = _get_settings()
    return await credits.check_balance_tool(
        cache, user_id,
        tier_config_json=settings.btcpay_tier_config,
        user_tiers_json=settings.btcpay_user_tiers,
        default_credit_ttl_seconds=settings.credit_ttl_seconds,
    )


# ---------------------------------------------------------------------------
# MCP Tools — Paid (Schwab brokerage data)
# ---------------------------------------------------------------------------


@tool
async def get_positions() -> str | dict[str, Any]:
    """Get current portfolio positions with options spread detection.

    Shows all open positions including equities and options.
    Options positions are automatically paired into spreads where possible,
    displaying credit received, max loss, current value, and P&L.

    Costs 5 api_sats.
    """
    gate = await _debit_or_error("get_positions")
    if gate:
        return gate

    try:
        user_id = _require_user_id()
        session = _require_session(user_id)
    except ValueError as e:
        await _rollback_debit("get_positions")
        return {"success": False, "error": str(e)}

    try:
        from tools.account import get_positions as _get_positions

        result_text = await _get_positions(session.client, session.account_hash)
        return result_text
    except Exception:
        await _rollback_debit("get_positions")
        raise


@tool
async def get_balances() -> str | dict[str, Any]:
    """Get account balances: cash, buying power, net liquidation value, and day P&L.

    Costs 5 api_sats.
    """
    gate = await _debit_or_error("get_balances")
    if gate:
        return gate

    try:
        user_id = _require_user_id()
        session = _require_session(user_id)
    except ValueError as e:
        await _rollback_debit("get_balances")
        return {"success": False, "error": str(e)}

    try:
        from tools.account import get_account_balances as _get_account_balances

        result_text = await _get_account_balances(session.client, session.account_hash)
        return result_text
    except Exception:
        await _rollback_debit("get_balances")
        raise


@tool
async def get_quote(symbols: str) -> str | dict[str, Any]:
    """Get real-time quotes for one or more symbols.

    Costs 5 api_sats.

    Args:
        symbols: Comma-separated ticker symbols (e.g. "AAPL,MSFT,TSLA").
    """
    gate = await _debit_or_error("get_quote")
    if gate:
        return gate

    try:
        user_id = _require_user_id()
        session = _require_session(user_id)
    except ValueError as e:
        await _rollback_debit("get_quote")
        return {"success": False, "error": str(e)}

    try:
        from tools.market import get_quote as _get_quote

        result_text = await _get_quote(session.client, symbols)
        return result_text
    except Exception:
        await _rollback_debit("get_quote")
        raise


@tool
async def get_option_chain(
    symbol: str,
    strike_count: int = 20,
    contract_type: str = "ALL",
    days_to_expiration: int = 21,
) -> str | dict[str, Any]:
    """Get filtered option chain for spread evaluation.

    Returns contracts filtered by DTE and open interest (>= 25),
    with Greeks, IV, and OTM percentage for efficient spread scanning.

    Costs 10 api_sats.

    Args:
        symbol: Underlying ticker symbol.
        strike_count: Number of strikes around ATM to include.
        contract_type: "ALL", "CALL", or "PUT".
        days_to_expiration: Maximum days to expiration to include.
    """
    gate = await _debit_or_error("get_option_chain")
    if gate:
        return gate

    try:
        user_id = _require_user_id()
        session = _require_session(user_id)
    except ValueError as e:
        await _rollback_debit("get_option_chain")
        return {"success": False, "error": str(e)}

    try:
        from tools.options import get_option_chain as _get_option_chain

        result_text = await _get_option_chain(
            session.client, symbol, strike_count, contract_type, days_to_expiration,
        )
        return result_text
    except Exception:
        await _rollback_debit("get_option_chain")
        raise


@tool
async def get_price_history(
    symbol: str,
    period_type: str = "month",
    period: int = 1,
    frequency_type: str = "daily",
    frequency: int = 1,
) -> str | dict[str, Any]:
    """Get historical OHLCV price data for trend analysis.

    Costs 10 api_sats.

    Args:
        symbol: Ticker symbol.
        period_type: "day", "month", "year", or "ytd".
        period: Number of periods.
        frequency_type: "minute", "daily", "weekly", or "monthly".
        frequency: Frequency interval.
    """
    gate = await _debit_or_error("get_price_history")
    if gate:
        return gate

    try:
        user_id = _require_user_id()
        session = _require_session(user_id)
    except ValueError as e:
        await _rollback_debit("get_price_history")
        return {"success": False, "error": str(e)}

    try:
        from tools.market import get_price_history as _get_price_history

        result_text = await _get_price_history(
            session.client, symbol, period_type, period, frequency_type, frequency,
        )
        return result_text
    except Exception:
        await _rollback_debit("get_price_history")
        raise


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    settings = _get_settings()
    mcp.run(
        transport="streamable-http",
        host=settings.schwab_mcp_host,
        port=settings.schwab_mcp_port,
    )
