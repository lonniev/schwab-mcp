#!/usr/bin/env python3
"""Diagnostic: simulate the actual cold-start flow end-to-end.

Tests whether courier.receive() → callback → _operator_credentials works.
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

        # Try manual courier.receive() to see what the callback gets
        print("\n=== Manual courier.receive() ===")
        try:
            from pynostr.key import PrivateKey
            settings = server._get_settings()
            pk = PrivateKey.from_nsec(settings.tollbooth_nostr_operator_nsec)
            operator_npub = pk.public_key.bech32()

            courier = server._get_courier_service()
            result = await courier.receive(
                operator_npub, service="schwab-operator",
            )
            print(f"  courier.receive() result keys: {list(result.keys())}")
            print(f"  success: {result.get('success')}")
            print(f"  callback_error: {result.get('callback_error')}")
            print(f"  operator_credentials_vaulted: "
                  f"{result.get('operator_credentials_vaulted')}")
            print(f"  fields_received: {result.get('fields_received')}")
            print(f"  encryption: {result.get('encryption')}")
            print(f"  _operator_credentials after: "
                  f"{server._operator_credentials}")
        except Exception as exc:
            print(f"  courier.receive() failed: {exc}")


if __name__ == "__main__":
    asyncio.run(main())
