"""Tests for vault module — per-user session management."""

import json
import time
from unittest.mock import MagicMock, patch

import pytest


def _make_mock_client():
    """Create a mock AsyncClient."""
    client = MagicMock()
    client.close_async_session = MagicMock(return_value=None)
    return client


def test_set_and_get_session():
    """set_session stores a session retrievable by get_session."""
    from vault import _sessions, get_session, set_session

    _sessions.clear()

    client = _make_mock_client()
    session = set_session(
        user_id="user-1",
        token_json='{"access_token": "tok"}',
        account_hash="hash123",
        client=client,
        npub="npub1abc",
    )

    assert session.token_json == '{"access_token": "tok"}'
    assert session.account_hash == "hash123"
    assert session.client is client
    assert session.npub == "npub1abc"

    retrieved = get_session("user-1")
    assert retrieved is session

    _sessions.clear()


def test_get_session_returns_none_for_unknown():
    """get_session returns None for unknown user."""
    from vault import _sessions, get_session

    _sessions.clear()
    assert get_session("unknown-user") is None


def test_get_session_expires():
    """get_session returns None for expired sessions."""
    from vault import SESSION_TTL_SECONDS, _sessions, get_session, set_session

    _sessions.clear()

    client = _make_mock_client()
    session = set_session("user-2", '{"t": "x"}', "hash", client)
    # Backdate creation
    session.created_at = time.time() - SESSION_TTL_SECONDS - 1

    assert get_session("user-2") is None
    assert "user-2" not in _sessions

    _sessions.clear()


@pytest.mark.asyncio
async def test_clear_session():
    """clear_session removes session and closes client."""
    from vault import _dpyc_sessions, _sessions, clear_session, set_session

    _sessions.clear()
    _dpyc_sessions.clear()

    client = MagicMock()

    async def mock_close():
        pass

    client.close_async_session = mock_close

    set_session("user-3", '{"t": "x"}', "hash", client, npub="npub1xyz")
    assert get_session_helper("user-3") is not None

    await clear_session("user-3")
    assert "user-3" not in _sessions
    assert "user-3" not in _dpyc_sessions

    _sessions.clear()
    _dpyc_sessions.clear()


def get_session_helper(user_id):
    from vault import get_session
    return get_session(user_id)


def test_get_dpyc_npub():
    """get_dpyc_npub returns npub when set."""
    from vault import _dpyc_sessions, _sessions, get_dpyc_npub, set_session

    _sessions.clear()
    _dpyc_sessions.clear()

    client = _make_mock_client()
    set_session("user-4", '{"t": "x"}', "hash", client, npub="npub1test")
    assert get_dpyc_npub("user-4") == "npub1test"
    assert get_dpyc_npub("unknown") is None

    _sessions.clear()
    _dpyc_sessions.clear()


def test_session_repr():
    """UserSession repr redacts sensitive fields."""
    from vault import UserSession

    session = UserSession(
        token_json='{"secret": "value"}',
        account_hash="hash123",
        client=_make_mock_client(),
        npub="npub1test",
    )
    repr_str = repr(session)
    assert "redacted" in repr_str
    assert "secret" not in repr_str
    assert "hash123" not in repr_str


def test_create_client_from_token():
    """_create_client_from_token creates async client with correct params."""
    with patch("vault.schwab.auth.client_from_access_functions") as mock_create:
        mock_create.return_value = _make_mock_client()

        from vault import _create_client_from_token

        client = _create_client_from_token(
            client_id="op_id",
            client_secret="op_secret",
            token_json='{"access_token": "user_tok"}',
        )

        mock_create.assert_called_once()
        call_kwargs = mock_create.call_args
        assert call_kwargs.kwargs["api_key"] == "op_id"
        assert call_kwargs.kwargs["app_secret"] == "op_secret"
        assert call_kwargs.kwargs["asyncio"] is True
        assert client is not None
