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

    @pytest.mark.asyncio
    async def test_returns_session_when_present(self):
        """_require_session returns the active session."""
        npub = "npub1test" + "0" * 51
        session = _make_mock_session()
        with patch("vault.get_session", return_value=session) as mock_get:
            from server import _require_session

            result = await _require_session(npub)
            assert result is session
            mock_get.assert_called_once_with(npub)

    @pytest.mark.asyncio
    async def test_raises_when_no_session(self):
        """_require_session raises ValueError when no npub provided."""
        from server import _require_session

        with pytest.raises(ValueError, match="npub is required"):
            await _require_session("")


class TestToolRegistry:
    """Tests for TOOL_REGISTRY categories (keyed by UUID)."""

    @staticmethod
    def _by_capability(registry, cap):
        """Look up identity by capability name."""
        return next(ti for ti in registry.values() if ti.capability == cap)

    def test_oauth_tools_in_standard_identities(self):
        """OAuth tools are now standard (from wheel), not domain-specific."""
        from tollbooth.tool_identity import STANDARD_IDENTITIES

        caps = {ti.capability for ti in STANDARD_IDENTITIES.values()}
        assert "begin_oauth" in caps
        assert "check_oauth_status" in caps

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


def _mock_resolve_service(collector_url="https://collector.example.com"):
    """Return an AsyncMock for resolve_service_by_name returning *collector_url*."""
    return AsyncMock(
        return_value={
            "npub": "npub1advocate",
            "url": collector_url,
            "name": "tollbooth-oauth2-collector",
        }
    )


    # OAuth tool tests removed — begin_oauth/check_oauth_status are now
    # standard wheel tools tested in tollbooth-dpyc.
