"""Tests for server — _require_session situation handling and tool registry."""

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


VALID_NPUB = "npub1l94pd4qu4eszrl6ek032ftcnsu3tt9a7xvq2zp7eaxeklp6mrpzssmq8pf"


class TestResolutionFor:
    """The situation→error_code mapping is the contract calling agents see."""

    def test_token_expired_maps_to_oauth_refresh_needed(self):
        from server import _resolution_for
        result = _resolution_for("token_expired")
        assert result["success"] is False
        assert result["error_code"] == "oauth_refresh_needed"
        assert any("schwab_begin_oauth" in step for step in result["next_steps"])

    def test_no_credentials_maps_to_oauth_refresh_needed(self):
        from server import _resolution_for
        result = _resolution_for("no_credentials")
        assert result["error_code"] == "oauth_refresh_needed"
        assert any("schwab_begin_oauth" in step for step in result["next_steps"])

    def test_no_account_hash_maps_to_account_hash_required(self):
        from server import _resolution_for
        result = _resolution_for("no_account_hash")
        assert result["error_code"] == "account_hash_required"
        assert any("schwab_get_account_numbers" in step for step in result["next_steps"])

    def test_vault_bootstrapping_maps_to_warming_up(self):
        from server import _resolution_for
        result = _resolution_for("vault_bootstrapping")
        assert result["error_code"] == "warming_up"

    def test_operator_not_configured_maps_through(self):
        from server import _resolution_for
        result = _resolution_for("operator_not_configured")
        assert result["error_code"] == "operator_not_configured"

    def test_unknown_situation_falls_back_to_no_credentials(self):
        from server import _resolution_for
        result = _resolution_for("some_new_situation_we_havent_seen")
        # Falls through to oauth_refresh_needed (the no_credentials default)
        assert result["error_code"] == "oauth_refresh_needed"


class TestRequireSession:
    """_require_session always returns a UserSession or a structured error dict."""

    @pytest.mark.asyncio
    async def test_missing_npub_returns_npub_invalid_dict(self):
        from server import _require_session
        result = await _require_session("")
        assert isinstance(result, dict)
        assert result["error_code"] == "npub_invalid"

    @pytest.mark.asyncio
    async def test_non_npub_prefix_returns_npub_invalid_dict(self):
        from server import _require_session
        result = await _require_session("not-an-npub")
        assert isinstance(result, dict)
        assert result["error_code"] == "npub_invalid"

    @pytest.mark.asyncio
    async def test_token_expired_returns_oauth_refresh_needed_dict(self):
        """Patron's refresh token aged out — surfaces as a structured dict, not raise."""
        import server as srv

        with patch.object(
            srv.runtime, "restore_oauth_session",
            new=AsyncMock(return_value=(None, "token_expired")),
        ):
            result = await srv._require_session(VALID_NPUB)

        assert isinstance(result, dict)
        assert result["error_code"] == "oauth_refresh_needed"
        assert any("schwab_begin_oauth" in step for step in result["next_steps"])

    @pytest.mark.asyncio
    async def test_no_account_hash_returns_account_hash_required_dict(self):
        """OAuth fine, but no account selected yet."""
        import server as srv

        creds = {
            "access_token": "tok",
            "token_json": '{"access_token": "tok"}',
            "account_hash": "",
        }
        with patch.object(
            srv.runtime, "restore_oauth_session",
            new=AsyncMock(return_value=(creds, "")),
        ):
            result = await srv._require_session(VALID_NPUB)

        assert isinstance(result, dict)
        assert result["error_code"] == "account_hash_required"

    @pytest.mark.asyncio
    async def test_operator_creds_missing_returns_operator_not_configured(self):
        """Operator hasn't delivered Schwab app credentials yet."""
        import server as srv

        creds = {
            "access_token": "tok",
            "token_json": '{"access_token": "tok"}',
            "account_hash": "hash123",
        }
        with (
            patch.object(
                srv.runtime, "restore_oauth_session",
                new=AsyncMock(return_value=(creds, "")),
            ),
            patch.object(
                srv, "_ensure_operator_credentials",
                new=AsyncMock(side_effect=ValueError("not delivered")),
            ),
        ):
            result = await srv._require_session(VALID_NPUB)

        assert isinstance(result, dict)
        assert result["error_code"] == "operator_not_configured"

    @pytest.mark.asyncio
    async def test_success_returns_user_session(self):
        """Happy path: returns a UserSession with a SchwabClient ready to use."""
        import server as srv
        from vault import UserSession

        creds = {
            "access_token": "tok",
            "token_json": '{"access_token": "tok"}',
            "account_hash": "hash123",
            "refresh_token": "rt",
        }
        with (
            patch.object(
                srv.runtime, "restore_oauth_session",
                new=AsyncMock(return_value=(creds, "")),
            ),
            patch.object(
                srv, "_ensure_operator_credentials",
                new=AsyncMock(return_value={"client_id": "id", "client_secret": "sec"}),
            ),
            patch("vault._create_client", return_value=MagicMock()) as mock_create,
        ):
            result = await srv._require_session(VALID_NPUB)

        assert isinstance(result, UserSession)
        assert result.account_hash == "hash123"
        # The SchwabClient is constructed with an on_token_refresh callback
        # so any in-memory refresh is persisted back to the vault.
        _, kwargs = mock_create.call_args
        assert kwargs.get("on_token_refresh") is not None


class TestToolRegistry:
    """Tool registry categories (keyed by UUID)."""

    @staticmethod
    def _by_capability(registry, cap):
        return next(ti for ti in registry.values() if ti.capability == cap)

    def test_oauth_tools_in_standard_identities(self):
        """OAuth tools are standard wheel tools, not domain-specific."""
        from tollbooth.tool_identity import STANDARD_IDENTITIES

        caps = {ti.capability for ti in STANDARD_IDENTITIES.values()}
        assert "begin_oauth" in caps
        assert "check_oauth_status" in caps
        assert "check_proof_status" in caps

    def test_paid_tools_have_paid_category(self):
        from server import TOOL_REGISTRY
        paid = ("read", "write", "heavy")

        assert self._by_capability(TOOL_REGISTRY, "get_brokerage_positions").category in paid
        assert self._by_capability(TOOL_REGISTRY, "get_brokerage_balances").category in paid
        assert self._by_capability(TOOL_REGISTRY, "get_stock_quote").category in paid

    def test_heavy_tools_have_heavy_category(self):
        from server import TOOL_REGISTRY

        assert self._by_capability(TOOL_REGISTRY, "get_option_chain").category == "heavy"
        assert self._by_capability(TOOL_REGISTRY, "get_price_history").category == "heavy"
