"""Tests for server module — domain-specific Schwab behaviour."""

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


class TestGetRedirectUri:
    """Tests for _get_redirect_uri helper (registry-based collector discovery)."""

    @pytest.mark.asyncio
    async def test_uses_registry_collector_url(self):
        """_get_redirect_uri resolves callback URL from DPYC registry."""
        mock_svc = {
            "url": "https://callback.web.val.run",
            "npub": "npub1...",
            "name": "tollbooth-oauth2-callback",
        }
        with patch(
            "tollbooth.resolve_service_by_name",
            new_callable=AsyncMock,
            return_value=mock_svc,
        ):
            from server import _get_redirect_uri

            result = await _get_redirect_uri()

        assert result == "https://callback.web.val.run"

    @pytest.mark.asyncio
    async def test_raises_when_registry_fails(self):
        """_get_redirect_uri raises RuntimeError when registry lookup fails."""
        with patch(
            "tollbooth.resolve_service_by_name",
            new_callable=AsyncMock,
            side_effect=Exception("registry unavailable"),
        ):
            from server import _get_redirect_uri

            with pytest.raises(RuntimeError, match="Failed to resolve"):
                await _get_redirect_uri()


def _mock_registry(collector_url="https://collector.example.com"):
    """Return a mock DPYCRegistry whose resolve_service_by_name returns *collector_url*."""
    mock_reg = AsyncMock()
    mock_reg.resolve_service_by_name = AsyncMock(
        return_value={
            "npub": "npub1advocate",
            "url": collector_url,
            "name": "tollbooth-oauth2-collector",
        }
    )
    return mock_reg


class TestCheckOAuthViaCollector:
    """Tests for _check_oauth_via_collector (registry-based discovery, npub-as-state)."""

    @pytest.mark.asyncio
    async def test_pending_when_code_not_ready(self):
        """Returns pending when collector has no code yet."""
        mock_reg = _mock_registry()
        with (
            patch(
                "server._get_settings",
                return_value=MagicMock(dpyc_registry_cache_ttl_seconds=300),
            ),
            patch("tollbooth.registry.DPYCRegistry", return_value=mock_reg),
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
        mock_settings.dpyc_registry_cache_ttl_seconds = 300

        mock_token = {
            "access_token": "at-123",
            "refresh_token": "rt-456",
            "expires_at": time.time() + 1800,
        }

        mock_client = MagicMock()
        mock_reg = _mock_registry()

        with (
            patch("server._get_settings", return_value=mock_settings),
            patch("tollbooth.registry.DPYCRegistry", return_value=mock_reg),
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
        npub_match = (
            call_kwargs.kwargs.get("npub") == "npub1patron"
            or call_kwargs[1].get("npub") == "npub1patron"
        )
        assert npub_match

    @pytest.mark.asyncio
    async def test_returns_error_when_registry_fails(self):
        """Returns error when registry lookup for collector fails."""
        from tollbooth.registry import RegistryError

        mock_reg = AsyncMock()
        mock_reg.resolve_service_by_name = AsyncMock(
            side_effect=RegistryError("No active member with service")
        )

        with (
            patch(
                "server._get_settings",
                return_value=MagicMock(dpyc_registry_cache_ttl_seconds=300),
            ),
            patch("tollbooth.registry.DPYCRegistry", return_value=mock_reg),
        ):
            from server import _check_oauth_via_collector

            result = await _check_oauth_via_collector("user-1", "npub1abc")

        assert result["success"] is False
        assert "Failed to resolve" in result["error"]

    @pytest.mark.asyncio
    async def test_returns_failed_on_token_exchange_error(self):
        """Returns failed when token exchange raises an exception."""
        mock_reg = _mock_registry()

        with (
            patch(
                "server._get_settings",
                return_value=MagicMock(dpyc_registry_cache_ttl_seconds=300),
            ),
            patch("tollbooth.registry.DPYCRegistry", return_value=mock_reg),
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
