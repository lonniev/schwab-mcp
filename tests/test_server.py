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
                    "client_id": "op_id",
                    "client_secret": "op_secret",
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
                patch("server._get_courier_service", side_effect=Exception("no courier")),
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
            "npub1x", {"client_id": "x"}, "schwab-operator"  # missing client_secret
        )
        assert result == {}


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
