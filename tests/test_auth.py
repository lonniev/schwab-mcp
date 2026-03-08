"""Tests for auth module."""

import subprocess
import sys


def test_cli_bootstrap_exits_with_error():
    """Running auth.py as __main__ prints help and exits 1."""
    result = subprocess.run(
        [sys.executable, "auth.py"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "Secure Courier" in result.stdout
