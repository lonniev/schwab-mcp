"""Tests for auth module."""

import json
import os
from unittest.mock import MagicMock, patch

import pytest


def test_read_token_from_env():
    """Token is loaded from SCHWAB_TOKEN_JSON env var."""
    from auth import _read_token_from_env

    token = {"access_token": "test_access", "refresh_token": "test_refresh"}
    with patch.dict(os.environ, {"SCHWAB_TOKEN_JSON": json.dumps(token)}):
        result = _read_token_from_env()
        assert result["access_token"] == "test_access"
        assert result["refresh_token"] == "test_refresh"


def test_read_token_from_env_missing():
    """Raises when SCHWAB_TOKEN_JSON is not set."""
    from auth import _read_token_from_env

    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(EnvironmentError):
            _read_token_from_env()


def test_write_token_noop_logs_warning(caplog):
    """Token write callback logs a warning about stale env var."""
    import logging

    from auth import _write_token_noop

    with caplog.at_level(logging.WARNING):
        _write_token_noop({"access_token": "new"})
    assert "stale" in caplog.text.lower()


def test_create_user_client_passes_asyncio_true():
    """create_user_client passes operator creds + user token + asyncio=True."""
    with patch("auth.schwab.auth.client_from_access_functions") as mock_create:
        mock_create.return_value = MagicMock()
        with patch.dict(
            os.environ,
            {
                "SCHWAB_CLIENT_ID": "test_id",
                "SCHWAB_CLIENT_SECRET": "test_secret",
            },
        ):
            from auth import create_user_client

            token_json = json.dumps({"access_token": "user_token"})
            client = create_user_client(token_json)

            mock_create.assert_called_once()
            call_kwargs = mock_create.call_args
            assert call_kwargs.kwargs.get("asyncio") is True or (
                len(call_kwargs.args) > 4 and call_kwargs.args[4] is True
            )
            assert call_kwargs.kwargs.get("api_key") == "test_id"
            assert call_kwargs.kwargs.get("app_secret") == "test_secret"
            assert client is not None


def test_create_user_client_requires_operator_creds():
    """create_user_client raises when operator creds are missing."""
    from auth import create_user_client

    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(EnvironmentError, match="SCHWAB_CLIENT_ID"):
            create_user_client('{"access_token": "x"}')
