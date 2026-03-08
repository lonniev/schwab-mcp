"""Tests for SchwabClient — httpx wrapper with bearer auth + token refresh."""

import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from schwab_client import _REFRESH_LEEWAY_SECONDS, SchwabClient


def _fresh_token(expires_in: int = 1800) -> dict:
    """Return a token dict that expires in `expires_in` seconds."""
    return {
        "access_token": "tok_abc",
        "refresh_token": "ref_xyz",
        "expires_at": time.time() + expires_in,
    }


def _expired_token() -> dict:
    """Return a token dict that is already expired."""
    return {
        "access_token": "tok_old",
        "refresh_token": "ref_xyz",
        "expires_at": time.time() - 100,
    }


@pytest.fixture
def client():
    """SchwabClient with a fresh token and mocked httpx."""
    c = SchwabClient("cid", "csecret", _fresh_token(), "https://api.schwabapi.com")
    c._http = AsyncMock()
    return c


@pytest.fixture
def expired_client():
    """SchwabClient with an expired token and mocked httpx."""
    c = SchwabClient("cid", "csecret", _expired_token(), "https://api.schwabapi.com")
    c._http = AsyncMock()
    return c


class TestTokenRefresh:
    """Token refresh logic."""

    @pytest.mark.asyncio
    async def test_no_refresh_when_token_valid(self, client):
        """_ensure_token does not refresh if token is still valid."""
        client._http.post = AsyncMock()  # should not be called
        await client._ensure_token()
        client._http.post.assert_not_called()

    @pytest.mark.asyncio
    async def test_refresh_when_token_near_expiry(self):
        """_ensure_token refreshes when token expires within leeway."""
        token = _fresh_token(expires_in=_REFRESH_LEEWAY_SECONDS - 10)
        c = SchwabClient("cid", "csecret", token, "https://api.schwabapi.com")
        c._http = AsyncMock()

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "access_token": "tok_new",
            "expires_in": 1800,
            "refresh_token": "ref_new",
        }
        mock_resp.raise_for_status.return_value = None
        c._http.post.return_value = mock_resp

        await c._ensure_token()

        c._http.post.assert_called_once()
        assert c._token["access_token"] == "tok_new"
        assert c._token["refresh_token"] == "ref_new"

    @pytest.mark.asyncio
    async def test_refresh_when_expired(self, expired_client):
        """_ensure_token refreshes when token is already expired."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "access_token": "tok_refreshed",
            "expires_in": 1800,
        }
        mock_resp.raise_for_status.return_value = None
        expired_client._http.post.return_value = mock_resp

        await expired_client._ensure_token()

        expired_client._http.post.assert_called_once()
        assert expired_client._token["access_token"] == "tok_refreshed"

    @pytest.mark.asyncio
    async def test_refresh_uses_basic_auth(self, expired_client):
        """Token refresh sends Basic auth header with client_id:client_secret."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "access_token": "tok_new",
            "expires_in": 1800,
        }
        mock_resp.raise_for_status.return_value = None
        expired_client._http.post.return_value = mock_resp

        await expired_client._ensure_token()

        call_kwargs = expired_client._http.post.call_args
        headers = call_kwargs.kwargs.get("headers", call_kwargs[1].get("headers", {}))
        assert "Basic" in headers["Authorization"]


class TestGetRequests:
    """Convenience method URL + param building."""

    @pytest.mark.asyncio
    async def test_get_account(self, client):
        """get_account builds correct URL."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"securitiesAccount": {}}
        mock_resp.raise_for_status.return_value = None
        client._http.get.return_value = mock_resp

        result = await client.get_account("HASH123", fields="positions")

        client._http.get.assert_called_once()
        call_args = client._http.get.call_args
        assert "/trader/v1/accounts/HASH123" in call_args[0][0]
        assert call_args.kwargs["params"] == {"fields": "positions"}
        assert result == {"securitiesAccount": {}}

    @pytest.mark.asyncio
    async def test_get_account_no_fields(self, client):
        """get_account without fields sends no params."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"securitiesAccount": {}}
        mock_resp.raise_for_status.return_value = None
        client._http.get.return_value = mock_resp

        await client.get_account("HASH123")

        call_args = client._http.get.call_args
        assert call_args.kwargs["params"] is None

    @pytest.mark.asyncio
    async def test_get_quotes(self, client):
        """get_quotes joins symbols correctly."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"AAPL": {}, "MSFT": {}}
        mock_resp.raise_for_status.return_value = None
        client._http.get.return_value = mock_resp

        await client.get_quotes(["AAPL", "MSFT"])

        call_args = client._http.get.call_args
        assert "/marketdata/v1/quotes" in call_args[0][0]
        assert call_args.kwargs["params"]["symbols"] == "AAPL,MSFT"

    @pytest.mark.asyncio
    async def test_get_price_history(self, client):
        """get_price_history passes through kwargs."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"candles": []}
        mock_resp.raise_for_status.return_value = None
        client._http.get.return_value = mock_resp

        await client.get_price_history("AAPL", periodType="month", frequencyType="daily")

        call_args = client._http.get.call_args
        assert "/marketdata/v1/pricehistory" in call_args[0][0]
        params = call_args.kwargs["params"]
        assert params["symbol"] == "AAPL"
        assert params["periodType"] == "month"
        assert params["frequencyType"] == "daily"

    @pytest.mark.asyncio
    async def test_get_option_chain(self, client):
        """get_option_chain passes through kwargs."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"callExpDateMap": {}, "putExpDateMap": {}}
        mock_resp.raise_for_status.return_value = None
        client._http.get.return_value = mock_resp

        await client.get_option_chain("AAPL", contractType="PUT", strikeCount=10)

        call_args = client._http.get.call_args
        assert "/marketdata/v1/chains" in call_args[0][0]
        params = call_args.kwargs["params"]
        assert params["symbol"] == "AAPL"
        assert params["contractType"] == "PUT"
        assert params["strikeCount"] == 10

    @pytest.mark.asyncio
    async def test_bearer_auth_header(self, client):
        """All GET requests include Bearer auth header."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {}
        mock_resp.raise_for_status.return_value = None
        client._http.get.return_value = mock_resp

        await client.get_account("HASH")

        call_args = client._http.get.call_args
        headers = call_args.kwargs["headers"]
        assert headers["Authorization"] == "Bearer tok_abc"


class TestClose:
    """Client lifecycle."""

    @pytest.mark.asyncio
    async def test_close_calls_aclose(self, client):
        """close() calls httpx aclose()."""
        client._http.aclose = AsyncMock()
        await client.close()
        client._http.aclose.assert_called_once()
