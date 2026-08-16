"""Tests for oauth_flow module — Schwab-specific wrappers over tollbooth.oauth2_collector."""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from oauth_flow import (
    begin_oauth_flow,
    build_authorize_url,
    exchange_code_for_token,
    fetch_account_hash,
)

# NOTE: decrypt_collector_code / retrieve_code_from_collector are SDK-owned
# (tollbooth.oauth2_collector, NIP-44 sealed since 0.85.x) and tested there —
# schwab only re-exports them, so it no longer duplicates their tests here.

# ---------------------------------------------------------------------------
# build_authorize_url tests
# ---------------------------------------------------------------------------


class TestBuildAuthorizeUrl:
    """Tests for build_authorize_url."""

    def test_constructs_url(self):
        """build_authorize_url includes all required params."""
        url = build_authorize_url("my-key", "https://example.com/cb", "state123")
        assert "client_id=my-key" in url
        assert "redirect_uri=" in url
        assert "state=state123" in url
        assert "response_type=code" in url
        assert "scope=readonly" in url
        assert url.startswith("https://api.schwabapi.com/v1/oauth/authorize?")

    def test_npub_as_state(self):
        """build_authorize_url correctly encodes an npub as state."""
        url = build_authorize_url("key", "https://cb.example.com", "npub1abc123")
        assert "state=npub1abc123" in url


# ---------------------------------------------------------------------------
# begin_oauth_flow tests
# ---------------------------------------------------------------------------


class TestBeginOAuthFlow:
    """Tests for begin_oauth_flow (stateless — npub as state)."""

    def test_returns_pending_with_url(self):
        """begin_oauth_flow returns pending status with authorization URL."""
        result = begin_oauth_flow(
            patron_npub="npub1abc",
            client_id="my-app-key",
            redirect_uri="https://collector.example.com/oauth/callback",
        )
        assert result["status"] == "pending"
        assert "authorize_url" in result
        assert "api.schwabapi.com/v1/oauth/authorize" in result["authorize_url"]
        assert "state=npub1abc" in result["authorize_url"]

    def test_uses_npub_as_state(self):
        """The npub is used directly as the OAuth state parameter."""
        result = begin_oauth_flow(
            patron_npub="npub1patron123",
            client_id="key",
            redirect_uri="https://cb.example.com",
        )
        assert "state=npub1patron123" in result["authorize_url"]

    def test_idempotent(self):
        """Calling begin_oauth_flow twice with the same npub produces the same URL."""
        r1 = begin_oauth_flow("npub1same", "key", "https://cb.example.com")
        r2 = begin_oauth_flow("npub1same", "key", "https://cb.example.com")
        assert r1["authorize_url"] == r2["authorize_url"]

    def test_message_mentions_schwab(self):
        """The status message mentions Schwab as the provider."""
        result = begin_oauth_flow("npub1x", "key", "https://cb.example.com")
        assert "Schwab" in result["message"]


# ---------------------------------------------------------------------------
# exchange_code_for_token tests
# ---------------------------------------------------------------------------


class TestExchangeCodeForToken:
    """Tests for exchange_code_for_token."""

    @pytest.mark.asyncio
    async def test_exchanges_code(self):
        """exchange_code_for_token posts to Schwab and returns token with expires_at."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "access_token": "at-123",
            "refresh_token": "rt-456",
            "expires_in": 1800,
            "token_type": "Bearer",
        }
        # A real status code, not a MagicMock. tollbooth-dpyc 0.78.0 classifies
        # the response by `status_code >= 400` instead of calling
        # raise_for_status(), so an unset mock attribute now raises TypeError.
        # The old test passed only because raise_for_status() is a no-op on a
        # mock — it never exercised status handling at all.
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        mock_http = AsyncMock()
        mock_http.post.return_value = mock_response
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)

        with patch("tollbooth.oauth2_collector.httpx.AsyncClient", return_value=mock_http):
            token = await exchange_code_for_token(
                code="auth-code-xyz",
                client_id="app-key",
                client_secret="app-secret",
                redirect_uri="https://example.com/cb",
            )

        assert token["access_token"] == "at-123"
        assert token["refresh_token"] == "rt-456"
        assert "expires_at" in token
        assert token["expires_at"] > time.time()

        # Verify Basic auth header was used
        call_kwargs = mock_http.post.call_args
        assert "Basic" in call_kwargs.kwargs.get("headers", call_kwargs[1].get("headers", {})).get(
            "Authorization", ""
        )

        # Verify it posted to the Schwab token endpoint
        assert call_kwargs[0][0] == "https://api.schwabapi.com/v1/oauth/token"


# ---------------------------------------------------------------------------
# fetch_account_hash tests
# ---------------------------------------------------------------------------


class TestFetchAccountHash:
    """Tests for fetch_account_hash."""

    @pytest.mark.asyncio
    async def test_returns_first_hash(self):
        """fetch_account_hash returns the first account's hashValue."""
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {"accountNumber": "12345", "hashValue": "abc-hash-123"},
            {"accountNumber": "67890", "hashValue": "def-hash-456"},
        ]
        mock_response.raise_for_status = MagicMock()

        mock_http = AsyncMock()
        mock_http.get.return_value = mock_response
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)

        with patch("oauth_flow.httpx.AsyncClient", return_value=mock_http):
            result = await fetch_account_hash("access-token-xyz")

        assert result == "abc-hash-123"

    @pytest.mark.asyncio
    async def test_empty_accounts_raises(self):
        """fetch_account_hash raises ValueError when no accounts returned."""
        mock_response = MagicMock()
        mock_response.json.return_value = []
        mock_response.raise_for_status = MagicMock()

        mock_http = AsyncMock()
        mock_http.get.return_value = mock_response
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)

        with patch("oauth_flow.httpx.AsyncClient", return_value=mock_http):
            with pytest.raises(ValueError, match="No accounts found"):
                await fetch_account_hash("access-token-xyz")
