"""Tests for oauth_flow module — Schwab-specific wrappers over tollbooth.oauth2_collector."""

import base64
import hashlib
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from oauth_flow import (
    begin_oauth_flow,
    build_authorize_url,
    decrypt_collector_code,
    exchange_code_for_token,
    fetch_account_hash,
    retrieve_code_from_collector,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fake_encrypt(code: str, state: str) -> str:
    """Encrypt a code the same way the collector does (XOR + base64)."""
    key = hashlib.sha256(state.encode()).digest()
    code_bytes = code.encode()
    encrypted = bytes(c ^ key[i % 32] for i, c in enumerate(code_bytes))
    return base64.urlsafe_b64encode(encrypted).decode()


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


# ---------------------------------------------------------------------------
# Encryption / decryption tests
# ---------------------------------------------------------------------------


class TestDecryptCollectorCode:
    """Tests for decrypt_collector_code (XOR with SHA-256 keystream)."""

    def test_roundtrip(self):
        """decrypt_collector_code reverses the collector's encryption."""
        encrypted = _fake_encrypt("my-secret-code", "my-state-token")
        assert decrypt_collector_code(encrypted, "my-state-token") == "my-secret-code"

    def test_npub_as_state_roundtrip(self):
        """Encryption/decryption works with an npub as the state."""
        npub = "npub1qqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqq3aael2"
        code = "authorization-code-from-schwab"
        encrypted = _fake_encrypt(code, npub)
        assert decrypt_collector_code(encrypted, npub) == code

    def test_wrong_state_raises(self):
        """decrypt_collector_code with wrong state raises OAuthCollectorError."""
        from tollbooth.oauth2_collector import OAuthCollectorError

        encrypted = _fake_encrypt("my-secret-code", "correct-state")
        try:
            result = decrypt_collector_code(encrypted, "wrong-state")
            assert result != "my-secret-code"
        except OAuthCollectorError:
            pass  # Expected — wrong key produces invalid bytes


# ---------------------------------------------------------------------------
# retrieve_code_from_collector tests
# ---------------------------------------------------------------------------


class TestRetrieveCodeFromCollector:
    """Tests for retrieve_code_from_collector."""

    @pytest.mark.asyncio
    async def test_returns_decrypted_code_on_success(self):
        """Returns the decrypted code when collector has it."""
        state = "npub1abc123"
        encrypted = _fake_encrypt("auth-code-abc", state)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"code": encrypted}
        mock_response.raise_for_status = MagicMock()

        mock_http = AsyncMock()
        mock_http.get.return_value = mock_response
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)

        with patch("tollbooth.oauth2_collector.httpx.AsyncClient", return_value=mock_http):
            result = await retrieve_code_from_collector(
                "https://collector.example.com", state
            )

        assert result == "auth-code-abc"
        mock_http.get.assert_called_once_with(
            "https://collector.example.com/oauth/retrieve",
            params={"state": state},
        )

    @pytest.mark.asyncio
    async def test_returns_none_on_404(self):
        """Returns None when collector hasn't received the code yet."""
        mock_response = MagicMock()
        mock_response.status_code = 404

        mock_http = AsyncMock()
        mock_http.get.return_value = mock_response
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)

        with patch("tollbooth.oauth2_collector.httpx.AsyncClient", return_value=mock_http):
            result = await retrieve_code_from_collector(
                "https://collector.example.com", "npub1abc"
            )

        assert result is None

    @pytest.mark.asyncio
    async def test_strips_trailing_slash(self):
        """Strips trailing slash from collector URL."""
        state = "npub1xyz"
        encrypted = _fake_encrypt("xyz", state)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"code": encrypted}
        mock_response.raise_for_status = MagicMock()

        mock_http = AsyncMock()
        mock_http.get.return_value = mock_response
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)

        with patch("tollbooth.oauth2_collector.httpx.AsyncClient", return_value=mock_http):
            result = await retrieve_code_from_collector(
                "https://collector.example.com/", state
            )

        assert result == "xyz"
        mock_http.get.assert_called_once_with(
            "https://collector.example.com/oauth/retrieve",
            params={"state": state},
        )
