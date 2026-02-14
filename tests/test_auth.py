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


def test_create_client_calls_schwab_auth():
    """create_client uses client_from_access_functions."""
    with patch("auth.schwab.auth.client_from_access_functions") as mock_create:
        mock_create.return_value = MagicMock()
        with patch.dict(
            os.environ,
            {
                "SCHWAB_CLIENT_ID": "test_id",
                "SCHWAB_CLIENT_SECRET": "test_secret",
                "SCHWAB_TOKEN_JSON": '{"access_token": "x"}',
            },
        ):
            from auth import create_client

            client = create_client()
            mock_create.assert_called_once()
            assert client is not None
