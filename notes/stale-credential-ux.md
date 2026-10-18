# Stale-Credential UX: Map Routine Refreshes to Friendly Guidance

**Status:** Revised 2026-10-18 for tollbooth-dpyc 0.103, where identity moved onto the
connection. Earlier revisions described proofs carried as tool arguments; that protocol is gone.

## Two Things Can Go Stale

A Schwab call needs two things, and each lapses on its own clock:

1. **The patron's npub, proven on the connection.** Either the request is signed with the
   npub's nsec (NIP-98, `Authorization: Nostr …`), or the client is an OAuth *holder* whose
   wallet holds a grant for that npub, earned once by answering a Nostr DM. A signed request
   never goes stale. A holder's grant does, on an operator-chosen lifetime.
2. **The patron's Schwab OAuth grant.** `OperatorRuntime.restore_oauth_session()` loads,
   refreshes and persists it; schwab-mcp and excalibur-mcp both delegate to it.

## What Has Shipped

- **Proof on the connection.** Tools take `npub` alone. A connection that does not prove it
  gets `error_code: "proof_required"`, and the fix is the DM round trip:
  `request_npub_proof(patron_npub)` returns a `nonce`, the patron answers the DM, then
  `receive_npub_proof(patron_npub, nonce)` stores the grant in the holder's wallet.
  The challenge is bound to the holder that asked for it.
- **`check_proof_status(patron_npub)`** — free, no side effects. Reports whether this
  connection proves the npub and, for a holder, the grant's runtime-computed remaining life.
- **`upstream_auth_refresh_needed`** — a named code for a Schwab grant the runtime could not
  refresh. The patron re-runs `begin_oauth` / `check_oauth_status`.

## Premises Still True

- **Schwab access tokens last on the order of a week.** The short window is the auth-code →
  token exchange after the patron clicks Allow, so call `check_oauth_status` promptly after
  Allow. Phrase it as a behaviour; never print a duration.
- **No TTL is a contract.** Grant lifetimes are operator-configured and runtime-derived.
  Tool docstrings and error messages quote no number.

## Still Open

1. **Silent refresh on a live 401.** Confirm a paid call after a multi-day idle succeeds with
   no patron action, i.e. the paid-tool path calls `restore_oauth_session()` on a 401 and not
   only at cold start.
2. **`session_status` TTLs.** It reports the patron's stored upstream OAuth; confirm whether
   it should also report the holder grant's remaining life, or leave that to
   `check_proof_status`.

## Diagnostic Recipe

When a paid call fails:

1. `schwab_service_status` — operator healthy?
2. `schwab_check_proof_status(patron_npub)` — not valid → `request_npub_proof`, the patron
   answers the DM, then `receive_npub_proof(patron_npub, nonce)`.
3. `schwab_check_oauth_status(npub)` — not `completed` → `begin_oauth`, then
   `check_oauth_status` promptly after Allow.
4. Both fresh and it still fails → read the `error_code`, then the operator logs.
