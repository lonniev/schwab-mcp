"""Tests for oauth_flow module — state tokens, flow management, token exchange."""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from oauth_flow import (
    OAuthPendingState,
    _pending_states,
    begin_oauth_flow,
    build_authorize_url,
    check_oauth_status_for_user,
    exchange_code_for_token,
    fetch_account_hash,
    generate_state_token,
    handle_oauth_callback,
    validate_state_token,
)

# Deterministic test key
_TEST_KEY = b"test-signing-key-32bytes-long!!!"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_pending_states():
    """Ensure pending state store is clean for each test."""
    _pending_states.clear()
    yield
    _pending_states.clear()


# ---------------------------------------------------------------------------
# State token tests
# ---------------------------------------------------------------------------


class TestStateTokens:
    """HMAC-signed state token generation and validation."""

    def test_roundtrip(self):
        """A generated token validates with the same key."""
        token = generate_state_token(_TEST_KEY)
        assert validate_state_token(token, _TEST_KEY)

    def test_tampered_nonce(self):
        """A token with a modified nonce fails validation."""
        token = generate_state_token(_TEST_KEY)
        nonce, sig = token.split(".")
        tampered = "ff" + nonce[2:] + "." + sig
        assert not validate_state_token(tampered, _TEST_KEY)

    def test_wrong_key(self):
        """A token validated with a different key fails."""
        token = generate_state_token(_TEST_KEY)
        wrong_key = b"wrong-key-wrong-key-wrong-key!!!"
        assert not validate_state_token(token, wrong_key)

    def test_no_dot(self):
        """A token without a dot separator fails validation."""
        assert not validate_state_token("nodothere", _TEST_KEY)


# ---------------------------------------------------------------------------
# begin_oauth_flow tests
# ---------------------------------------------------------------------------


class TestBeginOAuthFlow:
    """Tests for begin_oauth_flow."""

    def test_creates_pending_state(self):
        """begin_oauth_flow creates a new pending state entry."""
        result = begin_oauth_flow(
            horizon_user_id="user-1",
            patron_npub="npub1abc",
            client_id="my-app-key",
            redirect_uri="https://example.com/callback",
            signing_key=_TEST_KEY,
        )
        assert result["status"] == "pending"
        assert "authorize_url" in result
        assert "api.schwabapi.com/v1/oauth/authorize" in result["authorize_url"]
        assert len(_pending_states) == 1

    def test_reuses_existing_flow(self):
        """begin_oauth_flow reuses a non-expired flow for the same user."""
        result1 = begin_oauth_flow(
            horizon_user_id="user-1",
            patron_npub="npub1abc",
            client_id="my-app-key",
            redirect_uri="https://example.com/callback",
            signing_key=_TEST_KEY,
        )
        result2 = begin_oauth_flow(
            horizon_user_id="user-1",
            patron_npub="npub1abc",
            client_id="my-app-key",
            redirect_uri="https://example.com/callback",
            signing_key=_TEST_KEY,
        )
        assert result1["authorize_url"] == result2["authorize_url"]
        assert len(_pending_states) == 1

    def test_cleans_expired_states(self):
        """begin_oauth_flow removes expired states."""
        # Inject an expired state
        _pending_states["old-token"] = OAuthPendingState(
            patron_npub="npub1old",
            horizon_user_id="user-old",
            created_at=time.time() - 700,  # > 600s TTL
        )

        begin_oauth_flow(
            horizon_user_id="user-new",
            patron_npub="npub1new",
            client_id="my-app-key",
            redirect_uri="https://example.com/callback",
            signing_key=_TEST_KEY,
        )
        assert "old-token" not in _pending_states
        assert len(_pending_states) == 1


# ---------------------------------------------------------------------------
# check_oauth_status_for_user tests
# ---------------------------------------------------------------------------


class TestCheckOAuthStatus:
    """Tests for check_oauth_status_for_user."""

    def test_pending(self):
        """Returns pending when flow is in progress."""
        begin_oauth_flow(
            horizon_user_id="user-1",
            patron_npub="npub1abc",
            client_id="key",
            redirect_uri="https://example.com/cb",
            signing_key=_TEST_KEY,
        )
        result = check_oauth_status_for_user("user-1")
        assert result["status"] == "pending"

    def test_completed(self):
        """Returns completed when flow finished successfully."""
        _pending_states["tok"] = OAuthPendingState(
            patron_npub="npub1abc",
            horizon_user_id="user-1",
            completed=True,
            result={"token": {}, "account_hash": "hash123"},
        )
        result = check_oauth_status_for_user("user-1")
        assert result["status"] == "completed"

    def test_failed(self):
        """Returns failed when flow completed with error."""
        _pending_states["tok"] = OAuthPendingState(
            patron_npub="npub1abc",
            horizon_user_id="user-1",
            completed=True,
            error="Token exchange failed",
        )
        result = check_oauth_status_for_user("user-1")
        assert result["status"] == "failed"
        assert "Token exchange" in result["error"]

    def test_no_flow(self):
        """Returns no_flow when no state exists for user."""
        result = check_oauth_status_for_user("user-unknown")
        assert result["status"] == "no_flow"


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

        with patch("oauth_flow.httpx.AsyncClient", return_value=mock_http):
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
# handle_oauth_callback tests
# ---------------------------------------------------------------------------


class TestHandleOAuthCallback:
    """Tests for handle_oauth_callback."""

    @pytest.mark.asyncio
    async def test_success(self):
        """handle_oauth_callback completes the flow on success."""
        state_token = generate_state_token(_TEST_KEY)
        _pending_states[state_token] = OAuthPendingState(
            patron_npub="npub1patron",
            horizon_user_id="user-1",
        )

        with (
            patch("oauth_flow.exchange_code_for_token", new_callable=AsyncMock) as mock_exchange,
            patch("oauth_flow.fetch_account_hash", new_callable=AsyncMock) as mock_fetch,
        ):
            mock_exchange.return_value = {
                "access_token": "at",
                "refresh_token": "rt",
                "expires_at": time.time() + 1800,
            }
            mock_fetch.return_value = "hash-abc"

            pending = await handle_oauth_callback(
                code="auth-code",
                state=state_token,
                signing_key=_TEST_KEY,
                client_id="key",
                client_secret="secret",
                redirect_uri="https://example.com/cb",
            )

        assert pending.completed is True
        assert pending.error is None
        assert pending.result["account_hash"] == "hash-abc"
        assert pending.result["token"]["access_token"] == "at"

    @pytest.mark.asyncio
    async def test_invalid_state(self):
        """handle_oauth_callback raises ValueError for invalid HMAC."""
        with pytest.raises(ValueError, match="Invalid state token"):
            await handle_oauth_callback(
                code="auth-code",
                state="bad.token",
                signing_key=_TEST_KEY,
                client_id="key",
                client_secret="secret",
                redirect_uri="https://example.com/cb",
            )

    @pytest.mark.asyncio
    async def test_expired_state(self):
        """handle_oauth_callback raises ValueError for expired state."""
        state_token = generate_state_token(_TEST_KEY)
        _pending_states[state_token] = OAuthPendingState(
            patron_npub="npub1patron",
            horizon_user_id="user-1",
            created_at=time.time() - 700,  # expired
        )

        with pytest.raises(ValueError, match="expired or not found"):
            await handle_oauth_callback(
                code="auth-code",
                state=state_token,
                signing_key=_TEST_KEY,
                client_id="key",
                client_secret="secret",
                redirect_uri="https://example.com/cb",
            )


# ---------------------------------------------------------------------------
# build_authorize_url test
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
