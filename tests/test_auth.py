"""Tests for auth module."""

import json
import os
from unittest.mock import MagicMock, patch

import pytest


def test_create_user_client_calls_vault_create_client():
    """create_user_client passes operator creds + user token to vault._create_client."""
    mock_client = MagicMock()
    with (
        patch("vault._create_client", return_value=mock_client) as mock_create,
        patch.dict(
            os.environ,
            {
                "SCHWAB_CLIENT_ID": "test_id",
                "SCHWAB_CLIENT_SECRET": "test_secret",
            },
        ),
    ):
        from auth import create_user_client

        token_json = json.dumps({"access_token": "user_token"})
        client = create_user_client(token_json)

        mock_create.assert_called_once_with(
            "test_id",
            "test_secret",
            token_json,
            api_base="https://api.schwabapi.com",
        )
        assert client is mock_client


def test_create_user_client_requires_operator_creds():
    """create_user_client raises when operator creds are missing."""
    from auth import create_user_client

    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(EnvironmentError, match="SCHWAB_CLIENT_ID"):
            create_user_client('{"access_token": "x"}')
