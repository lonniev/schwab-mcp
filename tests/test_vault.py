"""Tests for vault module — UserSession bundle + _create_client wiring."""

from unittest.mock import AsyncMock, MagicMock, patch


def _make_mock_client():
    """Create a mock SchwabClient."""
    client = MagicMock()
    client.close = AsyncMock()
    return client


def test_session_repr_redacts_sensitive_fields():
    """UserSession repr redacts token and account_hash."""
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


def test_create_client_passes_through_params():
    """_create_client constructs a SchwabClient with parsed token + on_token_refresh."""
    with patch("vault.SchwabClient") as mock_cls:
        mock_cls.return_value = _make_mock_client()

        from vault import _create_client

        cb = AsyncMock()
        _create_client(
            client_id="op_id",
            client_secret="op_secret",
            token_json='{"access_token": "user_tok"}',
            on_token_refresh=cb,
        )

        mock_cls.assert_called_once_with(
            "op_id",
            "op_secret",
            {"access_token": "user_tok"},
            "https://api.schwabapi.com",
            on_token_refresh=cb,
        )
