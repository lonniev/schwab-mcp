"""Registry metadata must not drift from the source-of-truth version.

``tollbooth.version.resolve_service_version`` reports ``pyproject [project].version``
as the live service version, but ``server.json`` carries a hand-maintained
``version`` that is published to the MCP Registry. If the two disagree, the
registry advertises a version the service never serves — the same class of
"what is actually deployed?" confusion that opened issue #62.
"""

import json
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_server_json_version_matches_pyproject():
    server_json = json.loads((ROOT / "server.json").read_text())
    with (ROOT / "pyproject.toml").open("rb") as fh:
        pyproject_version = tomllib.load(fh)["project"]["version"]
    assert server_json["version"] == pyproject_version, (
        f"server.json version {server_json['version']!r} drifted from "
        f"pyproject {pyproject_version!r}; bump server.json on every /release."
    )
