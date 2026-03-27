"""Tests for vault module — per-user session management."""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_mock_client():
    """Create a mock SchwabClient."""
    client = MagicMock()
    client.close = AsyncMock()
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


def get_session_helper(user_id):
    from vault import get_session
    return get_session(user_id)


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


def test_create_client():
    """_create_client creates SchwabClient with correct params."""
    with patch("vault.SchwabClient") as mock_cls:
        mock_cls.return_value = _make_mock_client()

        from vault import _create_client

        client = _create_client(
            client_id="op_id",
            client_secret="op_secret",
            token_json='{"access_token": "user_tok"}',
        )

        mock_cls.assert_called_once_with(
            "op_id",
            "op_secret",
            {"access_token": "user_tok"},
            "https://api.schwabapi.com",
        )
        assert client is not None
