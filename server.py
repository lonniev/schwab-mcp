"""Schwab MCP Server — multi-tenant brokerage data for Claude.ai.

Tollbooth-monetized, DPYC-native. Each user delivers their own Schwab
OAuth token + account hash via Secure Courier; per-user AsyncClient
instances are cached in memory. All brokerage tools are credit-gated
via the full Tollbooth DPYC monetization stack (Lightning micropayments).
"""

from __future__ import annotations

import asyncio
import importlib.metadata
import logging
import platform
from typing import Any

from fastmcp import FastMCP
from tollbooth.constants import ToolTier
from tollbooth.slug_tools import make_slug_tool

# _RESTRICTED may not be in older tollbooth releases — define sentinel
_RESTRICTED = getattr(ToolTier, "RESTRICTED", -1)

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

_DPYC_BANNER = {
    "powered_by": "DPYC Tollbooth — Don't Pester Your Customer",
    "logo": "https://raw.githubusercontent.com/lonniev/dpyc-community/main/assets/dpyc-logo.png",
    "tagline": (
        "Pre-funded Lightning micropayments for AI tool calls. "
        "No credit cards. No KYC. No interruptions. Just sats in, service out."
    ),
    "community": "https://github.com/lonniev/dpyc-community",
    "join": "Call the dpyc-oracle's how_to_join() tool to get started.",
    "oracle": "https://dpyc-oracle.fastmcp.app/mcp",
}

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
    "begin_oauth": ToolTier.FREE,
    "check_oauth_status": ToolTier.FREE,
    "service_status": ToolTier.FREE,
    "account_statement": ToolTier.FREE,
    "account_statement_infographic": ToolTier.READ,
    "restore_credits": ToolTier.FREE,
    "get_pricing_model": ToolTier.FREE,
    "list_constraint_types": ToolTier.FREE,
    "how_to_join": ToolTier.FREE,
    "get_tax_rate": ToolTier.FREE,
    "lookup_member": ToolTier.FREE,
    "network_advisory": ToolTier.FREE,
    # Restricted — operator only
    "set_pricing_model": _RESTRICTED,
    # Paid — READ tier (5 api_sats)
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


_cached_collector_url: str | None = None


async def _resolve_collector_url() -> str:
    """Resolve the OAuth2 collector URL from the DPYC registry."""
    global _cached_collector_url
    if _cached_collector_url is not None:
        return _cached_collector_url

    from tollbooth.registry import DEFAULT_REGISTRY_URL, DPYCRegistry, RegistryError

    settings = _get_settings()
    registry = DPYCRegistry(
        url=DEFAULT_REGISTRY_URL,
        cache_ttl_seconds=settings.dpyc_registry_cache_ttl_seconds,
    )
    try:
        svc = await registry.resolve_service_by_name("tollbooth-oauth2-collector")
    except RegistryError as e:
        raise RuntimeError(
            f"Failed to resolve OAuth2 collector from registry: {e}"
        ) from e
    finally:
        await registry.close()

    _cached_collector_url = svc["url"].rstrip("/")
    logger.info("Resolved OAuth2 collector URL: %s", _cached_collector_url)
    return _cached_collector_url


# ---------------------------------------------------------------------------
# Operator credential cache (delivered via Secure Courier)
# ---------------------------------------------------------------------------

_operator_credentials: dict[str, str] | None = None

# Well-known binding ID for operator credential session binding.
# Stored by receive_credentials(service="schwab-operator") so any Horizon
# worker process can discover the correct sender npub on cold start.
_OPERATOR_BINDING_ID = "__schwab_operator__"


async def _ensure_operator_credentials() -> dict[str, str]:
    """Return cached operator credentials, restoring from vault on cold start.

    Two-track cold-start restore:
    1. Session binding — resolve sender npub from persistent binding, then
       vault lookup under the correct npub.
    2. Operator npub — fall back to NSEC-derived npub (works when the
       operator used their own Nostr key to send the DM).

    Raises ValueError if operator credentials have not been delivered.
    """
    global _operator_credentials
    if _operator_credentials:
        return _operator_credentials

    courier = _get_courier_service()

    # Track 1: session binding → correct sender npub → vault restore
    try:
        await courier.ensure_identity(
            _OPERATOR_BINDING_ID, service="schwab-operator",
        )
        if _operator_credentials:
            logger.info("Operator credentials restored via session binding.")
            return _operator_credentials
    except Exception as exc:
        logger.debug("Operator cold-start via session binding: %s", exc)

    # Track 2: operator npub → vault restore (self-delivered case)
    try:
        operator_npub = _get_operator_npub()
        result = await courier.receive(operator_npub, service="schwab-operator")
        logger.info(
            "Operator credential cold-start (operator npub): success=%s, "
            "callback_error=%s",
            result.get("success"), result.get("callback_error"),
        )
        if _operator_credentials:
            return _operator_credentials
        logger.warning(
            "Vault restore returned success=%s but _operator_credentials "
            "still None. Result keys: %s",
            result.get("success"), list(result.keys()),
        )
    except Exception as exc:
        logger.warning("Operator credential cold-start restore failed: %s", exc)

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
    """Operator callback: handle credentials received via Secure Courier.

    Two services are supported:
    - "schwab-operator": stores app_key + secret (mapped to client_id/client_secret) in memory
    - "schwab": combines operator creds with patron's token_json + account_hash
      to create a per-user session
    """
    global _operator_credentials
    result: dict[str, Any] = {}

    # --- Operator credentials (global, one-time) ---
    # DM fields use Schwab UI names (app_key / secret); mapped internally
    # to client_id / client_secret for the OAuth flow.
    if service == "schwab-operator":
        if not all(k in credentials for k in ("app_key", "secret")):
            logger.warning(
                "schwab-operator callback: expected keys (app_key, secret) "
                "but got %s — skipping",
                list(credentials.keys()),
            )
            return result
        _operator_credentials = {
            "client_id": credentials["app_key"],
            "client_secret": credentials["secret"],
        }
        logger.info("Operator credentials activated in memory.")
        return {"operator_credentials_vaulted": True}

    # --- Patron credentials (per-user) ---
    if service != "schwab":
        return result

    user_id = _get_current_user_id()
    if not user_id:
        return result

    if not all(k in credentials for k in ("token_json", "account_hash")):
        return result

    try:
        op_creds = await _ensure_operator_credentials()
    except ValueError as e:
        return {"session_activated": False, "error": str(e)}

    settings = _get_settings()

    from vault import _create_client, set_session

    client = _create_client(
        op_creds["client_id"],
        op_creds["client_secret"],
        credentials["token_json"],
        api_base=settings.schwab_trader_api,
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
        "schwab-operator": CredentialTemplate(
            service="schwab-operator",
            version=1,
            fields={
                "app_key": FieldSpec(required=True, sensitive=True),
                "secret": FieldSpec(required=True, sensitive=True),
            },
            description="Schwab API app credentials (operator-provided)",
        ),
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

    # Pre-populate consumed event IDs from Neon so previously-drained
    # relay DMs are skipped without re-processing on cold start.
    try:
        asyncio.ensure_future(_load_consumed_ids())
    except RuntimeError:
        pass

    return _courier_service


# ---------------------------------------------------------------------------
# Stale relay DM drain helpers
# ---------------------------------------------------------------------------


async def _ensure_consumed_events_schema() -> None:
    """Create the consumed_relay_events table if it doesn't exist."""
    vault = _get_commerce_vault()
    await vault._execute(
        "CREATE TABLE IF NOT EXISTS consumed_relay_events ("
        "    event_id TEXT PRIMARY KEY,"
        "    service TEXT NOT NULL,"
        "    consumed_at TIMESTAMPTZ DEFAULT now()"
        ")"
    )


async def _load_consumed_ids() -> None:
    """Load persisted consumed event IDs from Neon into the exchange."""
    try:
        vault = _get_commerce_vault()
        await _ensure_consumed_events_schema()
        result = await vault._execute(
            "SELECT event_id FROM consumed_relay_events"
        )
        rows = result.get("rows", [])
        if not rows:
            return

        courier = _get_courier_service()
        exchange = courier._exchange
        event_ids = {row[0] if isinstance(row, (list, tuple)) else row["event_id"] for row in rows}
        with exchange._lock:
            exchange._consumed_ids.update(event_ids)
        logger.info("Loaded %d consumed event IDs from Neon.", len(event_ids))
    except Exception as exc:
        logger.debug("Failed to load consumed event IDs: %s", exc)


async def _persist_consumed_ids(event_ids: list[str], service: str) -> None:
    """Bulk-insert consumed event IDs into Neon. Prunes rows >7 days old."""
    if not event_ids:
        return
    try:
        vault = _get_commerce_vault()
        await _ensure_consumed_events_schema()
        for eid in event_ids:
            await vault._execute(
                "INSERT INTO consumed_relay_events (event_id, service) "
                "VALUES ($1, $2) ON CONFLICT DO NOTHING",
                [eid, service],
            )
        # Prune old rows
        await vault._execute(
            "DELETE FROM consumed_relay_events "
            "WHERE consumed_at < now() - INTERVAL '7 days'"
        )
    except Exception as exc:
        logger.warning("Failed to persist consumed event IDs: %s", exc)


async def _drain_stale_dms(sender_npub: str, service: str) -> int:
    """Drain stale relay DMs for a sender/service pair.

    Pops each candidate DM without sending an ack (no reply_npub/reason),
    so the NIP-09 deletion fires (daemon thread) but no slow synchronous
    ack DM is sent back.

    Returns the count of drained events.
    """
    try:
        courier = _get_courier_service()
        exchange = courier._exchange

        from pynostr.key import PublicKey  # type: ignore[import-untyped]

        sender_hex = PublicKey.from_npub(sender_npub).hex()

        # Fetch recent DMs into the buffer
        exchange._fetch_dms_from_relays()

        # Find matching unconsumed candidates
        candidates = exchange._find_dm_candidates(sender_hex)
        if not candidates:
            return 0

        drained_ids: list[str] = []
        for candidate in candidates:
            event_id = candidate.get("id", "")
            if not event_id:
                continue
            # Pop without reply — no ack DM, just NIP-09 deletion
            exchange._pop_event(event_id)
            drained_ids.append(event_id)

        if drained_ids:
            await _persist_consumed_ids(drained_ids, service)
            logger.info(
                "Drained %d stale relay DMs for %s (service=%s)",
                len(drained_ids), sender_npub, service,
            )

        return len(drained_ids)
    except Exception as exc:
        logger.debug("Drain stale DMs failed: %s", exc)
        return 0


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
# Pricing model store singleton
# ---------------------------------------------------------------------------

_pricing_store: Any = None


def _get_pricing_store() -> Any:
    global _pricing_store
    if _pricing_store is not None:
        return _pricing_store
    from tollbooth.pricing_store import PricingModelStore

    vault = _get_commerce_vault()
    _pricing_store = PricingModelStore(neon_vault=vault)

    try:
        asyncio.ensure_future(_pricing_store.ensure_schema())
    except RuntimeError:
        pass
    return _pricing_store


# ---------------------------------------------------------------------------
# ConstraintGate singleton
# ---------------------------------------------------------------------------

_gate: Any = None
_gate_initialized: bool = False


def _get_gate():
    """Return the ConstraintGate singleton, or None if constraints are off."""
    global _gate, _gate_initialized
    if _gate_initialized:
        return _gate
    from tollbooth import ConstraintGate

    settings = _get_settings()
    config = settings.to_tollbooth_config()
    if config.constraints_enabled:
        _gate = ConstraintGate(config)
    _gate_initialized = True
    return _gate


# ---------------------------------------------------------------------------
# Demand tracking helpers
# ---------------------------------------------------------------------------


def _demand_window_key() -> str:
    """Compute the current hourly demand window key (e.g. '2026-03-05T14:00')."""
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:00")


async def _get_global_demand(tool_name: str) -> dict[str, int]:
    """Read global demand for *tool_name* from Neon.  Returns {tool: count}.

    On error or when vault is unconfigured, returns empty dict (base pricing).
    """
    try:
        vault = _get_commerce_vault()
        count = await vault.get_demand(tool_name, _demand_window_key())
        return {tool_name: count}
    except Exception:
        return {}


def _fire_and_forget_demand_increment(tool_name: str) -> None:
    """Increment the demand counter for *tool_name* -- async, non-blocking."""

    async def _increment() -> None:
        try:
            vault = _get_commerce_vault()
            await vault.increment_demand(tool_name, _demand_window_key())
        except Exception:
            pass  # best-effort; stale counts just mean slightly off pricing

    asyncio.create_task(_increment())


# ---------------------------------------------------------------------------
# Oracle delegation
# ---------------------------------------------------------------------------


async def _call_oracle(
    tool_name: str, arguments: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Delegate a tool call to the DPYC Oracle."""
    try:
        from tollbooth.oracle_client import OracleClient
        from tollbooth import resolve_oracle_service

        oracle_url = await resolve_oracle_service()
        return await OracleClient(oracle_url).call_tool(tool_name, arguments)
    except Exception as e:
        return {"success": False, "error": f"Oracle delegation failed: {e}"}


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


async def _debit_or_error(tool_name: str, **kwargs: Any) -> dict[str, Any] | None:
    """Check balance and debit credits for a paid tool call.

    Returns None to proceed, or an error dict to short-circuit.
    Skips gating entirely in STDIO mode or when vault is unconfigured.

    RESTRICTED tools (cost == _RESTRICTED) are operator-only:
    allowed at cost 0 if the caller's npub matches the operator npub,
    rejected otherwise.  STDIO mode bypasses the restriction.
    """
    cost = TOOL_COSTS.get(tool_name, 0)

    # RESTRICTED tier: operator-only access gate
    if cost == _RESTRICTED:
        user_id = _get_current_user_id()
        if not user_id:
            return None  # STDIO mode — allow
        try:
            caller_npub = await _ensure_dpyc_session()
        except ValueError as e:
            return {"success": False, "error": str(e)}
        if caller_npub != _get_operator_npub():
            # Allow if caller provides a valid operator proof
            proof = kwargs.get("operator_proof")
            if proof:
                from tollbooth.operator_proof import verify_operator_proof

                if verify_operator_proof(proof, _get_operator_npub(), tool_name):
                    return None  # proof verified — allow
            return {
                "success": False,
                "error": "This tool is restricted to the operator.",
            }
        return None  # operator — allow at cost 0

    if cost == 0:
        return None

    # STDIO mode — no gating
    if not _get_current_user_id():
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

    # ConstraintGate may modify the cost or deny the call
    gate = _get_gate()
    if gate and gate.enabled:
        ledger = await cache.get(user_id)
        demand = await _get_global_demand(tool_name)
        denial, effective_cost = gate.check(
            tool_name=tool_name,
            base_cost=cost,
            ledger=ledger,
            npub=user_id,
            global_demand=demand,
        )
        if denial is not None:
            return denial
        cost = effective_cost

    # If constraint reduced cost to zero, skip debit
    if cost == 0:
        return None

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

    # Successful debit — increment global demand counter (fire-and-forget)
    _fire_and_forget_demand_increment(tool_name)

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

    # Try cold-start restore if operator creds aren't in memory
    if not _operator_credentials:
        try:
            await _ensure_operator_credentials()
        except (ValueError, RuntimeError):
            pass

    op_status = "configured" if _operator_credentials else "not_configured"

    if not user_id:
        return {
            "mode": "stdio",
            "message": "Running in STDIO mode (local dev).",
            "personal_session": False,
            "operator_credentials": op_status,
            "dpyc": _DPYC_BANNER,
        }

    session = get_session(user_id)
    if session:
        result: dict[str, Any] = {
            "mode": "cloud",
            "personal_session": True,
            "session_age_seconds": session.age_seconds,
            "message": "Personal Schwab credentials active.",
            "operator_credentials": op_status,
        }
        npub = get_dpyc_npub(user_id)
        if npub:
            result["dpyc_npub"] = npub
        else:
            result["dpyc_warning"] = "No DPYC identity active."
        result["dpyc"] = _DPYC_BANNER
        return result

    return {
        "mode": "cloud",
        "personal_session": False,
        "operator_credentials": op_status,
        "message": (
            "No active session. Follow the next_steps to onboard via "
            "Secure Courier -- credentials travel via encrypted Nostr DM "
            "and never appear in this chat."
        ),
        "next_steps": _ONBOARDING_NEXT_STEPS,
        "dpyc": _DPYC_BANNER,
    }


# ---------------------------------------------------------------------------
# MCP Tools — Secure Courier (Free)
# ---------------------------------------------------------------------------


@tool
async def request_credential_channel(
    service: str,
    recipient_npub: str | None = None,
) -> dict[str, Any]:
    """Open a Secure Courier channel for out-of-band credential delivery.

    If you provide your npub, the service sends you a welcome DM -- just
    open your Nostr client and reply to it with your credentials.

    How it works:
    1. Call this tool with your npub -- a welcome DM arrives in your Nostr inbox.
    2. Open your Nostr client (Primal, Damus, Amethyst, etc.).
    3. Reply with JSON matching the service template:
       - schwab-operator: {"app_key": "...", "secret": "..."}
       - schwab: {"token_json": "...", "account_hash": "..."}
    4. Return here and call receive_credentials with your npub.

    Your credentials never appear in this chat.

    Args:
        service: Which credential template to use ("schwab" or "schwab-operator").
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
    service: str,
) -> dict[str, Any]:
    """Pick up credentials delivered via the Secure Courier.

    If you've previously delivered credentials, they'll be returned
    from the encrypted vault without any relay I/O.

    Credential values are NEVER echoed back -- only the field count and
    service name are returned.

    Args:
        sender_npub: Your **patron** Nostr public key (npub1...).
        service: Which credential template to match ("schwab" or "schwab-operator").
    """
    try:
        courier = _get_courier_service()
    except (ValueError, RuntimeError) as e:
        return {"success": False, "error": str(e)}

    try:
        # Operator credentials use a well-known binding ID so any Horizon
        # worker can discover the sender npub on cold start.
        caller_id = (
            _OPERATOR_BINDING_ID
            if service == "schwab-operator"
            else _get_current_user_id()
        )
        result = await courier.receive(
            sender_npub, service=service, caller_id=caller_id,
        )
        # Sweep any remaining stale DMs that weren't consumed by receive
        drained = await _drain_stale_dms(sender_npub, service)
        if drained:
            result["stale_dms_drained"] = drained
        return result
    except Exception as e:
        return {"success": False, "error": str(e)}


@tool
async def forget_credentials(sender_npub: str, service: str) -> dict[str, Any]:
    """Delete vaulted AND in-memory credentials so you can re-deliver via Secure Courier.

    Use this when you've rotated your Schwab token and need to send fresh
    credentials through the diplomatic pouch.

    Args:
        sender_npub: Your Nostr public key (npub1...).
        service: Which service's credentials to forget ("schwab" or "schwab-operator").
    """
    global _operator_credentials

    try:
        courier = _get_courier_service()
    except (ValueError, RuntimeError) as e:
        return {"success": False, "error": str(e)}

    result = await courier.forget(
        sender_npub, service=service, caller_id=_get_current_user_id(),
    )
    drained = await _drain_stale_dms(sender_npub, service)
    result["relay_dms_drained"] = drained

    # Clear in-memory state — forget means forget
    if service == "schwab-operator":
        _operator_credentials = None
        result["operator_credentials_cleared"] = True
    elif service == "schwab":
        user_id = _get_current_user_id()
        if user_id:
            from vault import clear_session
            await clear_session(user_id)
            result["session_cleared"] = True

    return result


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
# OAuth collector helper
# ---------------------------------------------------------------------------


async def _check_oauth_via_collector(user_id: str, patron_npub: str) -> dict[str, Any]:
    """Poll the external OAuth2 collector for the auth code, then activate session.

    Uses the patron's npub as the OAuth state parameter — no server-side
    pending-state storage needed.
    """
    from oauth_flow import (
        exchange_code_for_token,
        fetch_account_hash,
        retrieve_code_from_collector,
    )

    try:
        collector_url = await _resolve_collector_url()
    except RuntimeError as e:
        return {"success": False, "error": str(e)}

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

    # Persist credentials + identity binding so cold-start restore works.
    # This mirrors what Secure Courier does on DM receipt: vault the
    # credentials, then store the caller_id → npub session binding.
    try:
        courier = _get_courier_service()
        courier._sessions[user_id] = patron_npub
        exchange = courier._exchange
        if exchange._credential_vault is not None:
            await exchange._credential_vault.ensure_schema()
            await exchange._vault_store("schwab", patron_npub, {
                "token_json": token_json,
                "account_hash": account_hash,
            })
            await courier._store_binding(user_id, "schwab", patron_npub)
            logger.info("OAuth credentials + binding persisted for %s", patron_npub)
        else:
            logger.warning("No credential vault — cannot persist OAuth session")
    except Exception as exc:
        logger.error("Failed to persist OAuth session: %s", exc)

    # Seed balance for new users
    await _seed_balance(patron_npub)

    return {"status": "completed", "message": "Session activated successfully."}


# ---------------------------------------------------------------------------
# MCP Tools — OAuth Flow (Free)
# ---------------------------------------------------------------------------


@tool
async def begin_oauth(patron_npub: str) -> dict[str, Any]:
    """Start the OAuth2 authorization flow to connect your Schwab account.

    Returns an authorization URL — open it in your browser to log in to
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
    if "authorize_url" in result:
        try:
            import httpx

            resp = await httpx.AsyncClient().get(
                "https://tinyurl.com/api-create.php",
                params={"url": result["authorize_url"]},
                timeout=5,
            )
            if resp.status_code == 200 and resp.text.startswith("https://"):
                result["authorize_url_full"] = result["authorize_url"]
                result["authorize_url"] = resp.text.strip()
        except Exception:
            pass  # Keep the full URL if shortener is unreachable

    return result


@tool
async def check_oauth_status(patron_npub: str) -> dict[str, Any]:
    """Check whether your OAuth authorization flow has completed.

    Call this after opening the authorization URL from begin_oauth
    and completing the Schwab login in your browser. Polls the external
    OAuth2 collector for the authorization code and activates the session.

    Args:
        patron_npub: The same DPYC patron npub used in begin_oauth.
    """
    try:
        user_id = _require_user_id()
    except ValueError as e:
        return {"success": False, "error": str(e)}

    return await _check_oauth_via_collector(user_id, patron_npub)


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


@tool
async def get_movers(
    index: str = "$SPX",
    sort: str = "PERCENT_CHANGE_UP",
    frequency: int = 0,
) -> str | dict[str, Any]:
    """Get top movers for a market index.

    Shows the biggest gainers, losers, or most active by volume.

    Costs 5 api_sats.

    Args:
        index: Index symbol — "$DJI", "$COMPX", or "$SPX".
        sort: "PERCENT_CHANGE_UP", "PERCENT_CHANGE_DOWN", or "VOLUME".
        frequency: 0 = all, 1 = 1-5%, 2 = 5-10%, 3 = 10-20%, 4 = 20%+.
    """
    gate = await _debit_or_error("get_movers")
    if gate:
        return gate

    try:
        user_id = _require_user_id()
        session = _require_session(user_id)
    except ValueError as e:
        await _rollback_debit("get_movers")
        return {"success": False, "error": str(e)}

    try:
        from tools.market import get_movers as _get_movers

        result_text = await _get_movers(session.client, index, sort, frequency)
        return result_text
    except Exception:
        await _rollback_debit("get_movers")
        raise


@tool
async def get_market_hours(
    markets: str = "equity,option",
    date: str = "",
) -> str | dict[str, Any]:
    """Get market hours for equity, option, bond, future, or forex markets.

    Useful for checking if markets are open, or pre/post-market session times.

    Costs 5 api_sats.

    Args:
        markets: Comma-separated: "equity", "option", "bond", "future", "forex".
        date: ISO date to check (e.g. "2026-03-15"). Defaults to today.
    """
    gate = await _debit_or_error("get_market_hours")
    if gate:
        return gate

    try:
        user_id = _require_user_id()
        session = _require_session(user_id)
    except ValueError as e:
        await _rollback_debit("get_market_hours")
        return {"success": False, "error": str(e)}

    try:
        from tools.market import get_market_hours as _get_market_hours

        result_text = await _get_market_hours(
            session.client, markets, date=date or None,
        )
        return result_text
    except Exception:
        await _rollback_debit("get_market_hours")
        raise


@tool
async def search_instruments(
    symbol: str,
    projection: str = "symbol-search",
) -> str | dict[str, Any]:
    """Search for instruments by symbol, name, or CUSIP.

    Use "fundamental" projection to include P/E, dividend yield, and market cap.

    Costs 5 api_sats.

    Args:
        symbol: Search term — ticker, partial name, or CUSIP.
        projection: "symbol-search", "symbol-regex", "desc-search",
            "desc-regex", or "fundamental".
    """
    gate = await _debit_or_error("search_instruments")
    if gate:
        return gate

    try:
        user_id = _require_user_id()
        session = _require_session(user_id)
    except ValueError as e:
        await _rollback_debit("search_instruments")
        return {"success": False, "error": str(e)}

    try:
        from tools.market import search_instruments as _search_instruments

        result_text = await _search_instruments(
            session.client, symbol, projection=projection,
        )
        return result_text
    except Exception:
        await _rollback_debit("search_instruments")
        raise


@tool
async def get_orders(
    from_date: str = "",
    to_date: str = "",
    status_filter: str = "",
) -> str | dict[str, Any]:
    """Get order history for your account.

    Returns orders with symbol, type, legs, status, fill price, and timestamps.
    Multi-leg option spread orders include all legs. Defaults to last 30 days.

    Costs 15 api_sats.

    Args:
        from_date: Start date (ISO 8601, e.g. "2026-01-01"). Defaults to 30 days ago.
        to_date: End date (ISO 8601). Defaults to now.
        status_filter: Optional status filter (e.g. "FILLED", "CANCELED", "WORKING").
    """
    gate = await _debit_or_error("get_orders")
    if gate:
        return gate

    try:
        user_id = _require_user_id()
        session = _require_session(user_id)
    except ValueError as e:
        await _rollback_debit("get_orders")
        return {"success": False, "error": str(e)}

    try:
        from tools.account import get_orders as _get_orders

        result_text = await _get_orders(
            session.client,
            session.account_hash,
            from_date=from_date or None,
            to_date=to_date or None,
            status_filter=status_filter or None,
        )
        return result_text
    except Exception:
        await _rollback_debit("get_orders")
        raise


@tool
async def get_order(order_id: str) -> str | dict[str, Any]:
    """Get details for a single order by ID.

    Returns full order details including all legs, fills, and status.

    Costs 8 api_sats.

    Args:
        order_id: The Schwab order ID.
    """
    gate = await _debit_or_error("get_order")
    if gate:
        return gate

    try:
        user_id = _require_user_id()
        session = _require_session(user_id)
    except ValueError as e:
        await _rollback_debit("get_order")
        return {"success": False, "error": str(e)}

    try:
        from tools.account import get_order as _get_order

        result_text = await _get_order(session.client, session.account_hash, order_id)
        return result_text
    except Exception:
        await _rollback_debit("get_order")
        raise


@tool
async def get_transactions(
    from_date: str = "",
    to_date: str = "",
    transaction_types: str = "",
) -> str | dict[str, Any]:
    """Get transaction history for your account.

    Returns transactions including trades, dividends, and cash movements.
    Defaults to last 30 days.

    Costs 15 api_sats.

    Args:
        from_date: Start date (ISO 8601, e.g. "2026-01-01"). Defaults to 30 days ago.
        to_date: End date (ISO 8601). Defaults to now.
        transaction_types: Comma-separated types: TRADE, DIVIDEND, CASH_IN_OR_CASH_OUT, etc.
    """
    gate = await _debit_or_error("get_transactions")
    if gate:
        return gate

    try:
        user_id = _require_user_id()
        session = _require_session(user_id)
    except ValueError as e:
        await _rollback_debit("get_transactions")
        return {"success": False, "error": str(e)}

    try:
        from tools.account import get_transactions as _get_transactions

        result_text = await _get_transactions(
            session.client,
            session.account_hash,
            from_date=from_date or None,
            to_date=to_date or None,
            transaction_types=transaction_types or None,
        )
        return result_text
    except Exception:
        await _rollback_debit("get_transactions")
        raise


@tool
async def get_transaction(transaction_id: str) -> str | dict[str, Any]:
    """Get details for a single transaction by ID.

    Costs 8 api_sats.

    Args:
        transaction_id: The Schwab transaction ID.
    """
    gate = await _debit_or_error("get_transaction")
    if gate:
        return gate

    try:
        user_id = _require_user_id()
        session = _require_session(user_id)
    except ValueError as e:
        await _rollback_debit("get_transaction")
        return {"success": False, "error": str(e)}

    try:
        from tools.account import get_transaction as _get_transaction

        result_text = await _get_transaction(
            session.client, session.account_hash, transaction_id,
        )
        return result_text
    except Exception:
        await _rollback_debit("get_transaction")
        raise


# ---------------------------------------------------------------------------
# MCP Tools — Operator / Pricing (Restricted + Free)
# ---------------------------------------------------------------------------


@tool
async def get_pricing_model() -> dict[str, Any]:
    """Get the active pricing model for this operator. Free."""
    try:
        store = _get_pricing_store()
        operator = _get_operator_npub()
    except (ValueError, RuntimeError) as e:
        return {"status": "error", "error": str(e)}
    from tollbooth.tools.pricing import get_pricing_model_tool

    return await get_pricing_model_tool(store, operator)


@tool
async def set_pricing_model(model_json: str) -> dict[str, Any]:
    """Set or update the active pricing model.

    Free — operator self-service tool.

    Args:
        model_json: JSON string with pricing model data.
            May include "operator_proof" — a signed Nostr kind-27235 event
            JSON string proving operator identity when the caller's session
            npub differs from the operator npub.
    """
    # Extract operator_proof from inside model_json if present
    import json as _json
    operator_proof = ""
    try:
        parsed = _json.loads(model_json)
        if isinstance(parsed, dict) and "operator_proof" in parsed:
            operator_proof = parsed.pop("operator_proof", "")
            model_json = _json.dumps(parsed)
    except (ValueError, TypeError):
        pass

    err = await _debit_or_error("set_pricing_model", operator_proof=operator_proof)
    if err:
        return err
    try:
        store = _get_pricing_store()
        operator = _get_operator_npub()
    except (ValueError, RuntimeError) as e:
        return {"status": "error", "error": str(e)}

    from tollbooth.tools.pricing import set_pricing_model_tool

    return await set_pricing_model_tool(store, operator, model_json)


@tool
async def list_constraint_types() -> dict[str, Any]:
    """List all available constraint types and their parameter schemas.

    Returns the type, category, description, and parameter specs for
    every constraint that can be used in a pricing pipeline.

    Free — no credits required.
    """
    from tollbooth.tools.pricing import list_constraint_types as _list

    return {"status": "ok", "constraint_types": _list()}


# ---------------------------------------------------------------------------
# MCP Tools — Account Statement / Credit Recovery
# ---------------------------------------------------------------------------


@tool
async def account_statement() -> dict[str, Any]:
    """Get a structured account statement showing balance, deposits, and usage.

    Free — no credits required.
    """
    from tollbooth.tools import credits

    try:
        user_id = await _ensure_dpyc_session()
        cache = _get_ledger_cache()
    except ValueError as e:
        return {"success": False, "error": str(e)}

    return await credits.account_statement_tool(cache, user_id)


@tool
async def account_statement_infographic() -> dict[str, Any]:
    """Get a visual account statement infographic.

    Cost: 1 api_sat (READ tier).
    """
    err = await _debit_or_error("account_statement_infographic")
    if err:
        return err

    from tollbooth.tools import credits

    try:
        user_id = await _ensure_dpyc_session()
        cache = _get_ledger_cache()
    except ValueError as e:
        return {"success": False, "error": str(e)}

    data = await credits.account_statement_tool(cache, user_id)
    return {"success": True, "statement": data}


@tool
async def restore_credits(invoice_id: str) -> dict[str, Any]:
    """Restore credits from a previously paid Lightning invoice.

    Use this if credits were lost due to a server error after payment.
    Safe to call multiple times — idempotent.

    Free — no credits required.

    Args:
        invoice_id: The BTCPay invoice ID from purchase_credits.
    """
    from tollbooth.tools import credits

    try:
        user_id = await _ensure_dpyc_session()
        btcpay = _get_btcpay()
        cache = _get_ledger_cache()
    except ValueError as e:
        return {"success": False, "error": str(e)}

    settings = _get_settings()
    return await credits.restore_credits_tool(
        btcpay,
        cache,
        user_id,
        invoice_id,
        default_credit_ttl_seconds=settings.credit_ttl_seconds,
    )


# ---------------------------------------------------------------------------
# MCP Tools — Service Status
# ---------------------------------------------------------------------------


@tool
async def service_status() -> dict[str, Any]:
    """Check the health and configuration of this Schwab MCP service.

    Free — no authentication or credits required.
    """
    from tollbooth import ECOSYSTEM_LINKS

    versions: dict[str, str] = {
        "schwab_mcp": importlib.metadata.version("schwab-mcp"),
        "python": platform.python_version(),
    }
    for pkg in ("tollbooth-dpyc", "fastmcp"):
        try:
            versions[pkg.replace("-", "_")] = importlib.metadata.version(pkg)
        except importlib.metadata.PackageNotFoundError:
            versions[pkg.replace("-", "_")] = "unknown"

    settings = _get_settings()
    gate = _get_gate()
    return {
        "success": True,
        "service": "schwab-mcp",
        "slug": "schwab",
        "versions": versions,
        "constraints_enabled": gate.enabled if gate else False,
        "btcpay_configured": settings.btcpay_host is not None,
        "vault_configured": settings.neon_database_url is not None,
        "seed_balance_sats": settings.seed_balance_sats,
        "tool_costs": {k: int(v) for k, v in TOOL_COSTS.items() if v > 0},
        "ecosystem_links": ECOSYSTEM_LINKS,
    }


# ---------------------------------------------------------------------------
# MCP Tools — Oracle Delegation (Free)
# ---------------------------------------------------------------------------


@tool
async def how_to_join() -> dict[str, Any]:
    """Get DPYC onboarding instructions from the community Oracle.

    Free — no authentication or credits required.
    """
    return await _call_oracle("how_to_join")


@tool
async def get_tax_rate() -> dict[str, Any]:
    """Get the current DPYC certification tax rate from the Oracle.

    Free — no authentication or credits required.
    """
    return await _call_oracle("get_tax_rate")


@tool
async def lookup_member(npub: str) -> dict[str, Any]:
    """Look up a DPYC community member by their Nostr npub.

    Can look up any role's npub — citizen, operator, or authority.
    Free — no authentication or credits required.

    Args:
        npub: The Nostr public key (bech32 npub format) to look up.
    """
    return await _call_oracle("lookup_member", {"npub": npub})


@tool
async def network_advisory() -> dict[str, Any]:
    """Get active network advisories from the DPYC Oracle.

    Free — no authentication or credits required.
    """
    return await _call_oracle("network_advisory")


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
