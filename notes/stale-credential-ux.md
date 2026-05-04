# Stale-Credential UX: Map Routine Refreshes to Friendly Guidance

**Status:** Revised after v0.15.7 review. The original note (claude.ai-authored) baked in two
docstring-quoted values as facts that don't match reality. This revision corrects the premises
and narrows the open work.

## Background — What's Already Shipped

These were called out in the original note as "requested changes" but landed in v0.15.7
(deployed 2026-04-26, verified production 2026-04-27). Verify before reopening.

- **Proof cache survives operator restart.** Replaced session-scoped cache with poison-keyed
  proof (`sha256(poison):npub`) persisted in Neon. The application holds raw poison; the MCP
  stores only the hash. Survives unlimited FastMCP Cloud restart cycles. (See
  `project_v01507_state` memory.)
- **OAuth refresh-token flow is generic.** `OperatorRuntime.restore_oauth_session()` does
  load → refresh → persist. Both schwab-mcp and excalibur-mcp delegate to it.

What's **not** verified end-to-end: whether the paid-tool wrapper actually invokes
`restore_oauth_session()` on a 401 retry path during a live tool call, vs. only on cold
start. That's the first thing the retest should pin down.

## Premises to Throw Out

The original note quoted two specific numbers as fact. Both were docstring artifacts.

1. **"Schwab access tokens expire in ~30 minutes."** Wrong. Schwab access tokens last on the
   order of a week. The short window is the auth-code → token exchange after the user clicks
   Allow on the authorize_url — miss that and the dance restarts. So Failure Mode A as
   originally described (intra-session token aging) isn't a real failure pattern. Silent
   refresh exists for week-scale gaps and revocation, not for routine trading hours.

2. **"Proof cache 1-hour TTL default."** There is no fixed default. The TTL is operator-chosen
   and the value returned by `receive_npub_proof` is whatever the runtime computed for that
   call. Don't write code or error messages that assume any particular number.

These two errors share one root cause: precise example values in tool docstrings get treated
as the contract by reviewing LLMs, then propagate as fact into tickets and other docstrings.
Scrub the schwab-mcp tool descriptions on this pass so the next reviewer doesn't repeat it.

## What's Actually Worth Doing

All of this lands in **`tollbooth-dpyc`**, not in schwab-mcp. Per CLAUDE.md §3 DRY boundaries,
error mapping, proof status, OAuth refresh, and session-status shape are SDK concerns. Do it
once and `/sdk-sync` propagates to excalibur, thebrain, schwab, and future MCPs.

### 1. Structured Error Codes for Routine Refresh Situations

When a paid-tool call fails with what is actually a credential-refresh situation (not an
infrastructure error), return a named code instead of `"Tool execution failed. Check
operator logs."`. The structured code lets a calling LLM branch programmatically without
parsing prose.

For an upstream-API auth failure that the runtime cannot transparently refresh:

```json
{
  "success": false,
  "error_code": "upstream_auth_refresh_needed",
  "error": "Upstream API authorization needs to be re-granted. This is routine — your previous grant has been revoked or has aged out.",
  "next_steps": [
    "schwab_begin_oauth(npub=<patron_npub>)",
    "Open the authorize_url, log in, click Allow",
    "schwab_check_oauth_status(npub=<patron_npub>) promptly after Allow"
  ]
}
```

Note: no number for "promptly." The auth-code window is upstream-defined and short; quoting
"15-30 seconds" or "30 minutes" in metadata risks the same magic-number problem. Phrase as a
behavior ("call promptly after clicking Allow"), not a duration.

For a stale proof:

```json
{
  "success": false,
  "error_code": "proof_refresh_needed",
  "error": "Your npub-proof cache entry is no longer valid. This is routine — sign a fresh DM challenge and you're back.",
  "next_steps": [
    "request_npub_proof(patron_npub=<patron_npub>)",
    "Sign the DM challenge from your Nostr client",
    "receive_npub_proof(patron_npub=<patron_npub>)"
  ]
}
```

Implementation lives in the `paid_tool` / `debit_or_deny` path in `tollbooth-dpyc`. The two
distinct failure paths to map: proof verification rejection, and upstream-API auth failures
that survive a transparent refresh attempt.

### 2. Verify Silent Refresh Actually Fires on 401

Acceptance criterion: after a multi-day idle period, `schwab_get_brokerage_positions`
succeeds without user interaction. If `restore_oauth_session()` is only called at cold
start, the wrapper is missing an on-demand refresh path. Confirm before scoping new work.

### 3. Add `check_proof_status` Diagnostic

Mirror the shape of `check_oauth_status`: a free, no-side-effect tool that lets a caller
ask "is this proof_token still going to work?" without burning credits on a guaranteed
failure. Returns the runtime-computed remaining TTL — do not embed a default in the
docstring.

```python
check_proof_status(patron_npub: str, proof_token: str) ->
{
  "success": true,
  "status": "valid" | "expired" | "unknown",
  "expires_in_seconds": <runtime-computed>,
  "message": "..."
}
```

Lives in the SDK alongside the other proof tools. Available on every MCP.

### 4. Surface Real TTLs in `session_status`

Let clients refresh proactively rather than reactively. All numbers are runtime-derived,
not docstring-quoted:

```json
{
  "lifecycle": "ready",
  "operator_npub": "...",
  "upstream_oauth": {
    "access_token_expires_in_seconds": <runtime>,
    "refresh_token_expires_at": "<runtime>"
  },
  "current_patron_proof": {
    "proof_token": "...",
    "proven_npub": "...",
    "expires_in_seconds": <runtime>
  }
}
```

### 5. Scrub Magic Numbers from Tool Metadata

Pass through `schwab-mcp/tools/` and `tollbooth-dpyc` proof / OAuth / vault modules.
Anywhere a docstring says "default 1 hour" / "30 minute TTL" / "lasts ~7 days," replace
with "operator-configured" or "runtime-derived" or a pointer to the upstream provider's
docs. The fix to the underlying TTL-mismatch problem is to stop printing the number, not
to pick a different number.

## Acceptance Criteria

- A routine refresh situation returns `error_code` + `next_steps`, not the generic
  "Tool execution failed" string.
- Multi-day idle followed by a paid call succeeds without user interaction (silent
  refresh path verified live).
- After upstream-grant revocation, the same call returns
  `{error_code: "upstream_auth_refresh_needed", next_steps: [...]}`.
- After proof TTL expiry, a paid call returns
  `{error_code: "proof_refresh_needed", next_steps: [...]}`.
- `check_proof_status` exists in the SDK standard tool set and returns runtime-computed
  state with no side effects.
- `session_status` exposes upstream OAuth and patron-proof TTLs as runtime-derived values.
- No tool docstring or description in `schwab-mcp` or `tollbooth-dpyc` quotes a specific
  TTL, default, or token lifetime.

## Retest Plan (run before scoping new work)

The point is to find which acceptance criteria already pass on v0.15.7 and which need
fresh work. Run sequentially against a healthy operator.

1. `schwab_service_status` — confirm operator healthy.
2. `schwab_session_status` — confirm `lifecycle: ready`. Note the schema today; this is
   the baseline for the §4 expansion.
3. `schwab_check_oauth_status(patron_npub)` — record current state.
4. Make a paid call (`schwab_get_brokerage_positions` or similar). Record exact response
   shape on success and on each failure mode.
5. Force a long idle (multi-hour or multi-day if possible) and retry the paid call. Does
   silent refresh fire? Record the response.
6. After observed proof expiry, make a paid call without re-running
   `request_npub_proof` / `receive_npub_proof`. Record the response shape.
7. Restart the operator (FastMCP Cloud cold start) and immediately retry. Confirm
   poison-keyed proof survival behaves as memory claims.

The diagnostic flowchart (was step 3-4 in the original note) collapses once `error_code`
exists. Until then, this retest is the source of truth on which failure modes are still
opaque.

## Diagnostic Recipe (interim, until `error_code` ships)

When a paid call fails generically:

1. `schwab_service_status` — operator healthy?
2. `schwab_session_status` — `lifecycle: ready`?
3. `schwab_check_oauth_status(patron_npub)` — if not `completed`, run `begin_oauth`
   and complete the dance promptly after clicking Allow.
4. If OAuth is `completed` and the call still fails → assume stale proof, re-run
   `request_npub_proof` / `receive_npub_proof`.
5. If both are fresh and it still fails → check operator logs.
