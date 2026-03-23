#!/usr/bin/env python3
"""Diagnostic script: trace operator credential cold-start flow.

Tests the exact same code path as server.py but with step-by-step output.
Requires .env with TOLLBOOTH_NOSTR_OPERATOR_NSEC and NEON_DATABASE_URL.

Usage:
    uv run python diagnose_operator_creds.py
"""

from __future__ import annotations

import asyncio
import logging
import sys

logging.basicConfig(level=logging.DEBUG, format="%(name)s %(levelname)s: %(message)s")
logger = logging.getLogger("diagnose")


async def main() -> None:
    from settings import Settings

    settings = Settings()

    # 1. Check settings
    print("\n=== 1. Settings ===")
    print(f"  NSEC set: {bool(settings.tollbooth_nostr_operator_nsec)}")
    print(f"  NEON_DATABASE_URL set: {bool(settings.neon_database_url)}")

    if not settings.tollbooth_nostr_operator_nsec:
        print("  FATAL: TOLLBOOTH_NOSTR_OPERATOR_NSEC not set")
        sys.exit(1)
    if not settings.neon_database_url:
        print("  FATAL: NEON_DATABASE_URL not set")
        sys.exit(1)

    # 2. Derive operator npub
    print("\n=== 2. Operator identity ===")
    from pynostr.key import PrivateKey

    pk = PrivateKey.from_nsec(settings.tollbooth_nostr_operator_nsec)
    operator_npub = pk.public_key.bech32()
    print(f"  Operator npub: {operator_npub}")

    # 3. Connect to vault and check tables
    print("\n=== 3. Vault connectivity ===")
    from tollbooth.credential_vault_backend import SessionBindingBackend
    from tollbooth.vaults import NeonCredentialVault, NeonVault

    neon = NeonVault(database_url=settings.neon_database_url)
    cred_vault = NeonCredentialVault(neon_vault=neon)
    await cred_vault.ensure_schema()
    print("  Schema ensured (credentials + session_bindings tables)")

    is_binding_backend = isinstance(cred_vault, SessionBindingBackend)
    print(f"  SessionBindingBackend: {is_binding_backend}")

    # 4. Check what's in the credentials table for schwab-operator
    print("\n=== 4. Credential vault entries for 'schwab-operator' ===")
    result = await neon._execute(
        "SELECT service, npub, length(encrypted_blob) as blob_len, updated_at "
        "FROM credentials WHERE service = $1",
        ["schwab-operator"],
    )
    rows = result.get("rows", [])
    if rows:
        for row in rows:
            print(f"  service={row['service']}, npub={row['npub']}, "
                  f"blob_len={row['blob_len']}, updated_at={row['updated_at']}")
    else:
        print("  (none)")

    # 5. Check session bindings
    print("\n=== 5. Session bindings ===")
    result = await neon._execute(
        "SELECT caller_id, service, npub, updated_at FROM session_bindings "
        "WHERE service = $1",
        ["schwab-operator"],
    )
    rows = result.get("rows", [])
    if rows:
        for row in rows:
            print(f"  caller_id={row['caller_id']}, service={row['service']}, "
                  f"npub={row['npub']}, updated_at={row['updated_at']}")
    else:
        print("  (none — this is why cold-start fails!)")

    # 6. Check if __schwab_operator__ binding exists
    print("\n=== 6. Well-known operator binding ===")
    from server import _OPERATOR_BINDING_ID

    binding_npub = await cred_vault.fetch_session_binding(
        _OPERATOR_BINDING_ID, "schwab-operator",
    )
    print(f"  Binding ID: {_OPERATOR_BINDING_ID}")
    print(f"  Resolved npub: {binding_npub}")

    # 7. Check if credentials exist under operator npub
    print("\n=== 7. Vault lookup under operator npub ===")
    blob = await cred_vault.fetch_credentials("schwab-operator", operator_npub)
    print(f"  Found: {bool(blob)}")

    # 8. If binding exists, check vault under binding npub
    if binding_npub and binding_npub != operator_npub:
        print(f"\n=== 8. Vault lookup under binding npub ({binding_npub}) ===")
        blob2 = await cred_vault.fetch_credentials("schwab-operator", binding_npub)
        print(f"  Found: {bool(blob2)}")

    # 9. List ALL credential entries to see what npubs have schwab-operator creds
    print("\n=== 9. All credential npubs ===")
    result = await neon._execute(
        "SELECT npub FROM credentials WHERE service = $1",
        ["schwab-operator"],
    )
    rows = result.get("rows", [])
    for row in rows:
        npub = row["npub"]
        match = " <-- operator" if npub == operator_npub else ""
        print(f"  {npub}{match}")

    # 10. Summary
    print("\n=== Summary ===")
    has_creds = len([r for r in (result.get("rows", []))]) > 0
    has_binding = binding_npub is not None
    has_under_operator = blob is not None

    if has_creds and has_binding:
        print("  OK: Credentials in vault AND binding exists. Cold-start should work.")
    elif has_creds and not has_binding:
        print("  FIX NEEDED: Credentials in vault but NO binding.")
        print("  → Call receive_credentials(service='schwab-operator') with v0.7.2+ "
              "to create the binding.")
        cred_npub = rows[0]["npub"] if rows else None
        if cred_npub:
            print(f"  → Or manually create binding: "
                  f"INSERT INTO session_bindings (caller_id, service, npub) "
                  f"VALUES ('{_OPERATOR_BINDING_ID}', 'schwab-operator', "
                  f"'{cred_npub}')")
    elif not has_creds:
        print("  NO CREDS: No schwab-operator credentials in vault at all.")
    if has_under_operator:
        print("  Operator npub lookup would succeed (Track 2).")
    else:
        print("  Operator npub lookup would fail (Track 2 won't help).")


if __name__ == "__main__":
    asyncio.run(main())
