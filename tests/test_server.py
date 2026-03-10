"""Tests for server module — singletons, session resolution, credit gating."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_mock_session():
    """Create a mock UserSession with a mock client."""
    from vault import UserSession

    client = MagicMock()
    return UserSession(
        token_json='{"access_token": "test"}',
        account_hash="testhash",
        client=client,
        npub="npub1testuser",
    )


class TestRequireSession:
    """Tests for _require_session."""

    def test_returns_session_when_present(self):
        """_require_session returns the active session."""
        session = _make_mock_session()
        with patch("vault.get_session", return_value=session) as mock_get:
            from server import _require_session

            result = _require_session("user-1")
            assert result is session
            mock_get.assert_called_once_with("user-1")

    def test_raises_when_no_session(self):
        """_require_session raises ValueError when no session exists."""
        with patch("vault.get_session", return_value=None):
            from server import _require_session

            with pytest.raises(ValueError, match="No active Schwab session"):
                _require_session("user-1")


class TestSessionStatus:
    """Tests for session_status tool."""

    @pytest.mark.asyncio
    async def test_stdio_mode(self):
        """session_status returns stdio mode when no user_id."""
        with patch("server._get_current_user_id", return_value=None):
            from server import session_status

            result = await session_status()
            assert result["mode"] == "stdio"
            assert result["personal_session"] is False
            assert "operator_credentials" in result

    @pytest.mark.asyncio
    async def test_cloud_with_session(self):
        """session_status returns active session info."""
        session = _make_mock_session()
        with (
            patch("server._get_current_user_id", return_value="horizon-user-1"),
            patch("vault.get_session", return_value=session),
            patch("vault.get_dpyc_npub", return_value="npub1testuser"),
        ):
            from server import session_status

            result = await session_status()
            assert result["mode"] == "cloud"
            assert result["personal_session"] is True
            assert result["dpyc_npub"] == "npub1testuser"

    @pytest.mark.asyncio
    async def test_cloud_no_session(self):
        """session_status returns onboarding steps when no session."""
        with (
            patch("server._get_current_user_id", return_value="horizon-user-1"),
            patch("vault.get_session", return_value=None),
        ):
            from server import session_status

            result = await session_status()
            assert result["mode"] == "cloud"
            assert result["personal_session"] is False
            assert "next_steps" in result


class TestDebitOrError:
    """Tests for _debit_or_error credit gating."""

    @pytest.mark.asyncio
    async def test_free_tool_skips_gating(self):
        """Free tools (cost=0) return None immediately."""
        from server import _debit_or_error

        result = await _debit_or_error("session_status")
        assert result is None

    @pytest.mark.asyncio
    async def test_insufficient_balance(self):
        """Paid tool with insufficient balance returns error dict."""
        mock_cache = MagicMock()
        mock_cache.debit = AsyncMock(return_value=False)
        mock_ledger = MagicMock()
        mock_ledger.balance_api_sats = 2
        mock_cache.get = AsyncMock(return_value=mock_ledger)

        with (
            patch("server._ensure_dpyc_session", new_callable=AsyncMock, return_value="npub1x"),
            patch("server._get_ledger_cache", return_value=mock_cache),
        ):
            from server import _debit_or_error

            result = await _debit_or_error("get_positions")
            assert result is not None
            assert result["success"] is False
            assert "Insufficient balance" in result["error"]

    @pytest.mark.asyncio
    async def test_successful_debit(self):
        """Paid tool with sufficient balance returns None (proceed)."""
        mock_cache = MagicMock()
        mock_cache.debit = AsyncMock(return_value=True)

        with (
            patch("server._ensure_dpyc_session", new_callable=AsyncMock, return_value="npub1x"),
            patch("server._get_ledger_cache", return_value=mock_cache),
        ):
            from server import _debit_or_error

            result = await _debit_or_error("get_positions")
            assert result is None

    @pytest.mark.asyncio
    async def test_no_dpyc_session(self):
        """Paid tool without DPYC session returns error."""
        with patch(
            "server._ensure_dpyc_session",
            new_callable=AsyncMock,
            side_effect=ValueError("No DPYC identity"),
        ):
            from server import _debit_or_error

            result = await _debit_or_error("get_positions")
            assert result is not None
            assert result["success"] is False
            assert "No DPYC identity" in result["error"]


class TestOnSchwabCredentialsReceived:
    """Tests for _on_schwab_credentials_received callback."""

    @pytest.mark.asyncio
    async def test_operator_credentials_stored(self):
        """Callback with service='schwab-operator' stores creds in memory."""
        import server

        server._operator_credentials = None
        try:
            result = await server._on_schwab_credentials_received(
                sender_npub="npub1operator",
                credentials={
                    "app_key": "op_id",
                    "secret": "op_secret",
                },
                service="schwab-operator",
            )

            assert result["operator_credentials_vaulted"] is True
            assert server._operator_credentials == {
                "client_id": "op_id",
                "client_secret": "op_secret",
            }
        finally:
            server._operator_credentials = None

    @pytest.mark.asyncio
    async def test_patron_session_uses_operator_creds(self):
        """Callback with service='schwab' reads _operator_credentials to create client."""
        import server

        mock_client = MagicMock()
        server._operator_credentials = {
            "client_id": "op_id",
            "client_secret": "op_secret",
        }

        try:
            with (
                patch("server._get_current_user_id", return_value="horizon-user-1"),
                patch("server._get_settings") as mock_settings,
                patch("vault._create_client", return_value=mock_client) as mock_create,
                patch("vault.set_session"),
                patch("server._seed_balance", new_callable=AsyncMock, return_value=False),
            ):
                mock_settings_obj = MagicMock()
                mock_settings_obj.schwab_trader_api = "https://api.schwabapi.com"
                mock_settings_obj.seed_balance_sats = 0
                mock_settings.return_value = mock_settings_obj

                result = await server._on_schwab_credentials_received(
                    sender_npub="npub1patron",
                    credentials={
                        "token_json": '{"access_token": "user_tok"}',
                        "account_hash": "user_hash",
                    },
                    service="schwab",
                )

                assert result["session_activated"] is True
                assert result["dpyc_npub"] == "npub1patron"
                mock_create.assert_called_once_with(
                    "op_id", "op_secret", '{"access_token": "user_tok"}',
                    api_base="https://api.schwabapi.com",
                )
        finally:
            server._operator_credentials = None

    @pytest.mark.asyncio
    async def test_patron_fails_without_operator_creds(self):
        """Callback returns error when operator creds not delivered."""
        import server

        server._operator_credentials = None

        try:
            with (
                patch("server._get_current_user_id", return_value="horizon-user-1"),
                patch(
                    "server._ensure_operator_credentials",
                    new_callable=AsyncMock,
                    side_effect=ValueError("Schwab operator credentials not configured"),
                ),
            ):
                result = await server._on_schwab_credentials_received(
                    sender_npub="npub1patron",
                    credentials={
                        "token_json": '{"access_token": "user_tok"}',
                        "account_hash": "user_hash",
                    },
                    service="schwab",
                )

                assert result["session_activated"] is False
                assert "operator credentials" in result["error"].lower()
        finally:
            server._operator_credentials = None

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_user_id(self):
        """Callback returns empty dict when no Horizon user ID for patron service."""
        with patch("server._get_current_user_id", return_value=None):
            from server import _on_schwab_credentials_received

            result = await _on_schwab_credentials_received(
                "npub1x", {"token_json": "x", "account_hash": "y"}, "schwab"
            )
            assert result == {}

    @pytest.mark.asyncio
    async def test_returns_empty_when_missing_fields(self):
        """Callback returns empty dict when credentials missing required fields."""
        with patch("server._get_current_user_id", return_value="user-1"):
            from server import _on_schwab_credentials_received

            result = await _on_schwab_credentials_received(
                "npub1x", {"token_json": "x"}, "schwab"  # missing account_hash
            )
            assert result == {}

    @pytest.mark.asyncio
    async def test_operator_returns_empty_when_missing_fields(self):
        """Callback returns empty dict when operator creds missing required fields."""
        from server import _on_schwab_credentials_received

        result = await _on_schwab_credentials_received(
            "npub1x", {"app_key": "x"}, "schwab-operator"  # missing secret
        )
        assert result == {}


class TestDrainStaleDMs:
    """Tests for stale relay DM drain on forget and receive."""

    @pytest.mark.asyncio
    async def test_forget_drains_stale_dms(self):
        """forget_credentials calls _drain_stale_dms and includes count in result."""
        mock_courier = MagicMock()
        mock_courier.forget = AsyncMock(return_value={"success": True})

        with (
            patch("server._get_courier_service", return_value=mock_courier),
            patch("server._get_current_user_id", return_value="user-1"),
            patch("server._drain_stale_dms", new_callable=AsyncMock, return_value=3) as mock_drain,
        ):
            from server import forget_credentials

            result = await forget_credentials("npub1sender", "schwab")

            assert result["success"] is True
            assert result["relay_dms_drained"] == 3
            mock_drain.assert_called_once_with("npub1sender", "schwab")

    @pytest.mark.asyncio
    async def test_receive_drains_stale_dms(self):
        """receive_credentials calls _drain_stale_dms after successful receive."""
        mock_courier = MagicMock()
        mock_courier.receive = AsyncMock(return_value={"success": True, "service": "schwab"})

        with (
            patch("server._get_courier_service", return_value=mock_courier),
            patch("server._get_current_user_id", return_value="user-1"),
            patch("server._drain_stale_dms", new_callable=AsyncMock, return_value=2) as mock_drain,
        ):
            from server import receive_credentials

            result = await receive_credentials("npub1sender", "schwab")

            assert result["success"] is True
            assert result["stale_dms_drained"] == 2
            mock_drain.assert_called_once_with("npub1sender", "schwab")

    @pytest.mark.asyncio
    async def test_receive_no_drain_key_when_zero(self):
        """receive_credentials omits stale_dms_drained when drain returns 0."""
        mock_courier = MagicMock()
        mock_courier.receive = AsyncMock(return_value={"success": True})

        with (
            patch("server._get_courier_service", return_value=mock_courier),
            patch("server._get_current_user_id", return_value="user-1"),
            patch("server._drain_stale_dms", new_callable=AsyncMock, return_value=0),
        ):
            from server import receive_credentials

            result = await receive_credentials("npub1sender", "schwab")

            assert "stale_dms_drained" not in result

    @pytest.mark.asyncio
    async def test_drain_pops_without_ack(self):
        """_drain_stale_dms calls _pop_event with only event_id (no reply/reason)."""
        mock_exchange = MagicMock()
        mock_exchange._fetch_dms_from_relays = MagicMock()
        mock_exchange._find_dm_candidates = MagicMock(return_value=[
            {"id": "evt1", "created_at": 1000},
            {"id": "evt2", "created_at": 999},
        ])
        mock_exchange._pop_event = MagicMock()

        mock_courier = MagicMock()
        mock_courier._exchange = mock_exchange

        mock_pk = MagicMock()
        mock_pk.hex.return_value = "abcd1234"

        with (
            patch("server._get_courier_service", return_value=mock_courier),
            patch("server._persist_consumed_ids", new_callable=AsyncMock),
            patch("pynostr.key.PublicKey") as mock_pubkey_cls,
        ):
            mock_pubkey_cls.from_npub.return_value = mock_pk

            from server import _drain_stale_dms

            count = await _drain_stale_dms("npub1sender", "schwab")

            assert count == 2
            # Verify _pop_event called with ONLY event_id — no reply_npub or reason
            assert mock_exchange._pop_event.call_count == 2
            mock_exchange._pop_event.assert_any_call("evt1")
            mock_exchange._pop_event.assert_any_call("evt2")

    @pytest.mark.asyncio
    async def test_consumed_ids_loaded_on_init(self):
        """_load_consumed_ids populates exchange._consumed_ids from Neon."""
        import threading

        mock_exchange = MagicMock()
        mock_exchange._lock = threading.Lock()
        mock_exchange._consumed_ids = set()

        mock_courier = MagicMock()
        mock_courier._exchange = mock_exchange

        mock_vault = MagicMock()
        mock_vault._execute = AsyncMock(side_effect=[
            # First call: ensure_schema (CREATE TABLE)
            {"rows": []},
            # Second call: SELECT event_id
            {"rows": [["evt_old_1"], ["evt_old_2"]]},
        ])

        with (
            patch("server._get_courier_service", return_value=mock_courier),
            patch("server._get_commerce_vault", return_value=mock_vault),
        ):
            from server import _load_consumed_ids

            await _load_consumed_ids()

            assert "evt_old_1" in mock_exchange._consumed_ids
            assert "evt_old_2" in mock_exchange._consumed_ids


class TestToolCosts:
    """Tests for TOOL_COSTS table."""

    def test_free_tools_are_zero(self):
        from server import TOOL_COSTS

        free_tools = [
            "session_status", "request_credential_channel",
            "receive_credentials", "forget_credentials",
            "check_balance", "purchase_credits", "check_payment",
        ]
        for t in free_tools:
            assert TOOL_COSTS[t] == 0, f"{t} should be free"

    def test_paid_tools_have_cost(self):
        from server import TOOL_COSTS

        assert TOOL_COSTS["get_positions"] > 0
        assert TOOL_COSTS["get_balances"] > 0
        assert TOOL_COSTS["get_quote"] > 0
        assert TOOL_COSTS["get_option_chain"] > 0
        assert TOOL_COSTS["get_price_history"] > 0

    def test_heavy_tools_cost_more(self):
        from server import TOOL_COSTS

        assert TOOL_COSTS["get_option_chain"] > TOOL_COSTS["get_positions"]
        assert TOOL_COSTS["get_price_history"] > TOOL_COSTS["get_quote"]


class TestResolveCollectorUrl:
    """Tests for _resolve_collector_url (DPYC registry-based discovery)."""

    @pytest.fixture(autouse=True)
    def _clear_cache(self):
        """Clear the collector URL cache before each test."""
        import server
        server._cached_collector_url = None
        yield
        server._cached_collector_url = None

    @pytest.mark.asyncio
    async def test_resolves_from_registry(self):
        """Resolves collector URL via DPYCRegistry.resolve_service_by_name."""
        mock_settings = MagicMock()
        mock_settings.dpyc_registry_cache_ttl_seconds = 300

        mock_registry = AsyncMock()
        mock_registry.resolve_service_by_name = AsyncMock(
            return_value={
                "npub": "npub1advocate",
                "url": "https://collector.fastmcp.app/",
                "name": "tollbooth-oauth2-collector",
            }
        )

        with (
            patch("server._get_settings", return_value=mock_settings),
            patch("tollbooth.registry.DPYCRegistry", return_value=mock_registry),
        ):
            from server import _resolve_collector_url

            result = await _resolve_collector_url()

        assert result == "https://collector.fastmcp.app"  # trailing slash stripped
        mock_registry.resolve_service_by_name.assert_awaited_once_with(
            "tollbooth-oauth2-collector"
        )
        mock_registry.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_caches_result(self):
        """Second call returns cached URL without registry lookup."""
        import server

        server._cached_collector_url = "https://cached.example.com"
        result = await server._resolve_collector_url()
        assert result == "https://cached.example.com"

    @pytest.mark.asyncio
    async def test_raises_on_registry_error(self):
        """Raises RuntimeError when registry lookup fails."""
        from tollbooth.registry import RegistryError

        mock_settings = MagicMock()
        mock_settings.dpyc_registry_cache_ttl_seconds = 300

        mock_registry = AsyncMock()
        mock_registry.resolve_service_by_name = AsyncMock(
            side_effect=RegistryError("No active member with service")
        )

        with (
            patch("server._get_settings", return_value=mock_settings),
            patch("tollbooth.registry.DPYCRegistry", return_value=mock_registry),
        ):
            from server import _resolve_collector_url

            with pytest.raises(RuntimeError, match="Failed to resolve OAuth2 collector"):
                await _resolve_collector_url()

        mock_registry.close.assert_awaited_once()


class TestGetRedirectUri:
    """Tests for _get_redirect_uri helper (registry-based collector discovery)."""

    @pytest.mark.asyncio
    async def test_uses_registry_collector_url(self):
        """_get_redirect_uri resolves collector URL from DPYC registry."""
        with patch(
            "server._resolve_collector_url",
            new_callable=AsyncMock,
            return_value="https://collector.fastmcp.app",
        ):
            from server import _get_redirect_uri

            result = await _get_redirect_uri()

        assert result == "https://collector.fastmcp.app/oauth/callback"

    @pytest.mark.asyncio
    async def test_raises_when_registry_fails(self):
        """_get_redirect_uri raises RuntimeError when registry lookup fails."""
        with patch(
            "server._resolve_collector_url",
            new_callable=AsyncMock,
            side_effect=RuntimeError("Failed to resolve OAuth2 collector from registry"),
        ):
            from server import _get_redirect_uri

            with pytest.raises(RuntimeError, match="Failed to resolve"):
                await _get_redirect_uri()


class TestCheckOAuthViaCollector:
    """Tests for _check_oauth_via_collector (registry-based discovery, npub-as-state)."""

    @pytest.mark.asyncio
    async def test_pending_when_code_not_ready(self):
        """Returns pending when collector has no code yet."""
        with (
            patch(
                "server._resolve_collector_url",
                new_callable=AsyncMock,
                return_value="https://collector.example.com",
            ),
            patch(
                "oauth_flow.retrieve_code_from_collector",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            from server import _check_oauth_via_collector

            result = await _check_oauth_via_collector("user-1", "npub1abc")

        assert result["status"] == "pending"

    @pytest.mark.asyncio
    async def test_completes_session_on_code_received(self):
        """Activates session when collector returns an auth code."""
        import time

        mock_settings = MagicMock()
        mock_settings.schwab_trader_api = "https://api.schwabapi.com"

        mock_token = {
            "access_token": "at-123",
            "refresh_token": "rt-456",
            "expires_at": time.time() + 1800,
        }

        mock_client = MagicMock()

        with (
            patch("server._get_settings", return_value=mock_settings),
            patch(
                "server._resolve_collector_url",
                new_callable=AsyncMock,
                return_value="https://collector.example.com",
            ),
            patch(
                "server._ensure_operator_credentials",
                new_callable=AsyncMock,
                return_value={"client_id": "cid", "client_secret": "csec"},
            ),
            patch(
                "server._get_redirect_uri",
                new_callable=AsyncMock,
                return_value="https://collector.example.com/oauth/callback",
            ),
            patch(
                "oauth_flow.retrieve_code_from_collector",
                new_callable=AsyncMock,
                return_value="auth-code-xyz",
            ),
            patch(
                "oauth_flow.exchange_code_for_token",
                new_callable=AsyncMock,
                return_value=mock_token,
            ),
            patch(
                "oauth_flow.fetch_account_hash",
                new_callable=AsyncMock,
                return_value="hash-abc",
            ),
            patch("vault._create_client", return_value=mock_client),
            patch("vault.set_session") as mock_set_session,
            patch("server._seed_balance", new_callable=AsyncMock, return_value=False),
        ):
            from server import _check_oauth_via_collector

            result = await _check_oauth_via_collector("user-1", "npub1patron")

        assert result["status"] == "completed"
        assert "Session activated" in result["message"]
        # Verify npub was passed to set_session
        mock_set_session.assert_called_once()
        call_kwargs = mock_set_session.call_args
        assert call_kwargs.kwargs.get("npub") == "npub1patron" or call_kwargs[1].get("npub") == "npub1patron"

    @pytest.mark.asyncio
    async def test_returns_error_when_registry_fails(self):
        """Returns error when registry lookup for collector fails."""
        with patch(
            "server._resolve_collector_url",
            new_callable=AsyncMock,
            side_effect=RuntimeError("Failed to resolve OAuth2 collector from registry"),
        ):
            from server import _check_oauth_via_collector

            result = await _check_oauth_via_collector("user-1", "npub1abc")

        assert result["success"] is False
        assert "Failed to resolve" in result["error"]

    @pytest.mark.asyncio
    async def test_returns_failed_on_token_exchange_error(self):
        """Returns failed when token exchange raises an exception."""
        with (
            patch(
                "server._resolve_collector_url",
                new_callable=AsyncMock,
                return_value="https://collector.example.com",
            ),
            patch(
                "server._ensure_operator_credentials",
                new_callable=AsyncMock,
                return_value={"client_id": "cid", "client_secret": "csec"},
            ),
            patch(
                "server._get_redirect_uri",
                new_callable=AsyncMock,
                return_value="https://collector.example.com/oauth/callback",
            ),
            patch(
                "oauth_flow.retrieve_code_from_collector",
                new_callable=AsyncMock,
                return_value="auth-code-xyz",
            ),
            patch(
                "oauth_flow.exchange_code_for_token",
                new_callable=AsyncMock,
                side_effect=Exception("Token exchange failed"),
            ),
        ):
            from server import _check_oauth_via_collector

            result = await _check_oauth_via_collector("user-1", "npub1abc")

        assert result["status"] == "failed"
        assert "Token exchange failed" in result["error"]
