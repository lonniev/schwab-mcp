#!/usr/bin/env python3
"""Diagnostic: simulate the actual cold-start flow end-to-end.

Tests whether receive_from_vault() → callback → _operator_credentials works.
"""

from __future__ import annotations

import asyncio
import logging

logging.basicConfig(level=logging.DEBUG, format="%(name)s %(levelname)s: %(message)s")
logger = logging.getLogger("diagnose")


async def main() -> None:
    import server

    # Reset in-memory state to simulate cold start
    server._operator_credentials = None
    server._settings = None
    server._courier_service = None

    print("\n=== Cold-start: calling _ensure_operator_credentials() ===")
    print(f"  _operator_credentials before: {server._operator_credentials}")

    try:
        result = await server._ensure_operator_credentials()
        print(f"  SUCCESS: {result}")
        print(f"  _operator_credentials after: {server._operator_credentials}")
    except ValueError as e:
        print(f"  FAILED: {e}")
        print(f"  _operator_credentials after: {server._operator_credentials}")

        # Try the vault-only read to see what cold-start restore gets.
        # Since wheel 0.44.0, the relay drain (courier.receive) is strict and
        # dpop_token-scoped; cold-start session restore reads from the vault via
        # receive_from_vault (no dpop_token, no relay I/O).
        print("\n=== Manual receive_from_vault() ===")
        try:
            from pynostr.key import PrivateKey
            settings = server._get_settings()
            pk = PrivateKey.from_nsec(settings.tollbooth_nostr_operator_nsec)
            operator_npub = pk.public_key.bech32()

            courier = server._get_courier_service()
            result = await courier._exchange.receive_from_vault(
                operator_npub, service="schwab-operator",
            )
            print(f"  receive_from_vault() result keys: {list(result.keys())}")
            print(f"  success: {result.get('success')}")
            print(f"  callback_error: {result.get('callback_error')}")
            print(f"  operator_credentials_vaulted: "
                  f"{result.get('operator_credentials_vaulted')}")
            print(f"  fields_received: {result.get('fields_received')}")
            print(f"  encryption: {result.get('encryption')}")
            print(f"  _operator_credentials after: "
                  f"{server._operator_credentials}")
        except Exception as exc:
            print(f"  receive_from_vault() failed: {exc}")


if __name__ == "__main__":
    asyncio.run(main())
