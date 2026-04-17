# Changelog

All notable changes to this project will be documented in this file.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.10.0] — 2026-04-13

- security: add proof parameter to all tools with npub
- chore: pin tollbooth-dpyc>=0.5.0

## [0.9.0] — 2026-04-11

- remove Horizon OAuth dependency — sessions keyed by npub

## [0.8.10] — 2026-04-11

- chore: pin tollbooth-dpyc>=0.4.9 — credential validator fix

## [0.8.9] — 2026-04-11

- chore: pin tollbooth-dpyc>=0.4.8 — ncred fix, courier diagnostics

## [0.8.8] — 2026-04-11

- chore: pin tollbooth-dpyc>=0.4.6
- Add credential_validator: validates btcpay + app_key + secret

## [0.8.7] — 2026-04-11

- chore: pin tollbooth-dpyc>=0.4.0
- chore: pin tollbooth-dpyc>=0.3.3
- chore: pin tollbooth-dpyc>=0.3.2 — lazy MCP name resolution
- chore: pin tollbooth-dpyc>=0.3.1 — function name MCP stamping
- chore: pin tollbooth-dpyc>=0.3.0 — single tool identity model
- chore: pin tollbooth-dpyc>=0.2.17 for slug namespace filtering
- fix: wrap long line for E501 lint compliance
- fix: clarify comments — Schwab OAuth2, not Horizon
- chore: bump to v0.8.6, pin tollbooth-dpyc>=0.2.16
- rename tool functions to match capability strings
- chore: pin tollbooth-dpyc>=0.2.15 for closed-door billing gate
- chore: pin tollbooth-dpyc>=0.2.14
- chore: pin tollbooth-dpyc>=0.2.13
- fix: lint — line length in tests
- fix: tests use capability lookup, not short-name keys
- feat: UUID-keyed internals — paid_tool and registry use UUID, not short names
- chore: pin tollbooth-dpyc>=0.2.11
- chore: pin tollbooth-dpyc>=0.2.10
- fix: lint — trailing whitespace on blank line
- chore: pin tollbooth-dpyc>=0.2.9
- fix: remove hardcoded cost claims from tool docstrings
- chore: pin tollbooth-dpyc>=0.2.8
- chore: pin tollbooth-dpyc>=0.2.7
- chore: pin tollbooth-dpyc>=0.2.6 for reset_pricing_model
- chore: pin tollbooth-dpyc>=0.2.5
- chore: pin tollbooth-dpyc>=0.2.4 for security fix + legacy UUID fallback
- chore: pin tollbooth-dpyc>=0.2.3 for pricing cache invalidation
- fix: lint — import ordering
- feat: UUID-based tool identity — TOOL_COSTS → TOOL_REGISTRY
- fix: lint — import order, NpubField shared annotation for E501
- chore: pin tollbooth-dpyc>=0.2.0 — clean Neon schema isolation
- chore: pin tollbooth-dpyc>=0.1.173 for onboarding late-attach fix
- chore: pin tollbooth-dpyc>=0.1.171 — don't cache empty ledgers on cold start
- chore: pin tollbooth-dpyc>=0.1.170 for cold start fixes
- chore: pin tollbooth-dpyc>=0.1.169 for session_status lifecycle
- feat: use wheel's themed infographic, delete local copy, pin >=0.1.167
- fix: DRY cleanup — use wheel's resolve_service_by_name instead of inline DPYCRegistry
- chore: pin tollbooth-dpyc>=0.1.165 for demurrage constraint rename
- chore: pin tollbooth-dpyc>=0.1.164 for tranche_expiration constraint
- chore: pin tollbooth-dpyc>=0.1.163 for authority_client npub fix
- chore: pin tollbooth-dpyc>=0.1.162 for patron onboarding status
- fix: pin tollbooth-dpyc>=0.1.161
- chore: pin tollbooth-dpyc>=0.1.160
- fix: lifecycle-aware session guidance instead of generic error messages
- fix: distinguish vault-not-ready from no-credentials in session restore

## [0.8.5] — 2026-03-29

- chore: pin tollbooth-dpyc>=0.1.159, bump to v0.8.4
- refactor: use tollbooth.shortlinks.create_shortlink() utility
- refactor: adopt SessionCache, delete legacy _seed_balance
- refactor: adopt @runtime.paid_tool() decorator, annotate npub params, remove boilerplate
- fix: replace v.gd URL shortener with tollbooth-shortlinks MCP service
- chore: bump tollbooth-dpyc to >=0.1.155
- refactor: strip fastmcp.json to nsec-only
- change CI workflow
- chore: bump tollbooth-dpyc to >=0.1.152
- chore: require Python >=3.12 (matches Horizon)
- chore: bump tollbooth-dpyc to >=0.1.150
- fix: pass PATRON_CREDENTIAL_SERVICE to store/load patron session
- chore: bump tollbooth-dpyc to >=0.1.147
- chore: bump tollbooth-dpyc to >=0.1.144
- fix: remove unused import and string annotation (lint)
- chore: bump tollbooth-dpyc to >=0.1.143
- chore: use v.gd instead of is.gd (cleaner domain)
- fix: use is.gd shortener instead of deprecated TinyURL
- fix: remove deprecated TinyURL shortener from OAuth begin flow
- feat: persist patron OAuth sessions to Neon vault
- chore: bump tollbooth-dpyc to >=0.1.141 (fix swapped debit args)
- chore: bump tollbooth-dpyc to >=0.1.140 (force int on balance)
- fix: dynamic version from package metadata + bump wheel to >=0.1.139
- chore: bump tollbooth-dpyc to >=0.1.138 (str/int ledger fix)
- chore: force Horizon cold start
- chore: bump tollbooth-dpyc to >=0.1.137
- chore: bump tollbooth-dpyc to >=0.1.136
- chore: bump tollbooth-dpyc to >=0.1.135
- chore: bump tollbooth-dpyc to >=0.1.134
- chore: bump tollbooth-dpyc to >=0.1.132
- chore: bump tollbooth-dpyc to >=0.1.131
- chore: bump tollbooth-dpyc to >=0.1.128
- fix: remove test for deleted auth.py
- fix: line length in get_market_hours docstring (E501)
- chore: bump tollbooth-dpyc to >=0.1.127
- refactor: nsec-only Settings, operator credential template
- chore: force Horizon cold start
- chore: bump tollbooth-dpyc to >=0.1.126 (template-only fields in onboarding)
- fix: separate operator vs patron credential templates
- restore: _ONBOARDING_NEXT_STEPS for agent-only onboarding
- refactor: npub required in tool descriptions + dead code cleanup
- feat: credential field descriptions for user guidance
- chore: bump tollbooth-dpyc to >=0.1.109
- feat: restore operator-specific Secure Courier greeting
- chore: bump tollbooth-dpyc to >=0.1.108 (infographic restored)
- chore: bump tollbooth-dpyc to >=0.1.107
- fix: remove unused pytest import
- fix: remove tests for deleted _dpyc_sessions and standard tools
- fix: line length in tests (E501)
- fix: delete tests for DPYC boilerplate moved to wheel
- fix: remove unused asyncio and importlib.metadata imports (F401)
- refactor: use OperatorRuntime + register_standard_tools
- refactor: npub is required on all credit tools — no session cache
- refactor: _ensure_dpyc_session accepts explicit npub override

## [0.8.4] — 2026-03-22

- chore: sync uv.lock
- fix: resolve ruff lint errors blocking CI (unused imports + variables)

## [0.8.3] — 2026-03-22

- chore: bump version to 0.8.3 for release
- chore: bump tollbooth-dpyc to >=0.1.100 (notarization catalog + remove get_tax_rate)

## [0.8.2] — 2026-03-22

- chore: bump version to 0.8.2 for release
- chore: bump tollbooth-dpyc to >=0.1.98 (cache migration fix)
- chore: bump tollbooth-dpyc to >=0.1.97 (tranche TTL expiry)
- chore: sync uv.lock
- chore: bump tollbooth-dpyc to >=0.1.96 for pricing model bridge
- chore: bump tollbooth-dpyc to >=0.1.95 for certify_credits rename
- refactor: rename certifier.certify() to certify_credits()
- chore: bump tollbooth-dpyc to >=0.1.94 for rollback tranche expiry
- chore: nudge deploy for tollbooth-dpyc v0.1.93 PyPI release
- feat: add SVG infographic rendering for account_statement_infographic
- chore: bump tollbooth-dpyc to >=0.1.93
- chore: add fastmcp.json for Horizon deployment config
- fix: handle missing package metadata in service_status (#32)
- feat: report version provenance in service_status (#31)
- chore: nudge deploy for tollbooth-dpyc v0.1.92 release
- Merge pull request #30 from lonniev/chore/bump-tollbooth-0.1.92
- chore: bump tollbooth-dpyc to >=0.1.92 for ACL support
- fix: extract operator_proof from model_json instead of separate tool arg (#29)
- feat: wire catalog conformance check, fix stale test, bump to 0.8.1
- add a sample daily report graphic

## [0.8.1] — 2026-03-12

- feat: add movers, market hours, and instrument search tools (#28)
- Merge pull request #27 from lonniev/docs/cloud-deployment-readme
- docs: reframe setup as cloud deployment via FastMCP Cloud
- Merge pull request #26 from lonniev/docs/readme-polish-apache
- docs: add hero banner image (options risk profile)
- docs: Apache 2.0 license, Oxcart preference, DPYC trademarks, attribution

## [0.8.0] — 2026-03-11

- Merge pull request #25 from lonniev/feat/orders-transactions-readme
- feat: add order & transaction history endpoints + Getting Started README
- feat: add DPYC Tollbooth banner to session_status responses
- fix: parse option strikes and expirations from OCC symbol
- feat: shorten OAuth authorize URL via TinyURL for human-friendly UX
- fix: persist OAuth credentials + binding in Courier vault for cold-start restore
- fix: persist DPYC identity binding after OAuth session activation
- feat: resolve OAuth callback URL from registry
- chore: bump to v0.7.15 with tollbooth-dpyc >=0.1.87
- chore: bump to v0.7.14 to retrigger Horizon deploy

## [0.7.13] — 2026-03-10

- fix: use Horizon /mcp/ prefix for OAuth redirect URI
- chore: bump to v0.7.12 for Horizon redeploy

## [0.7.11] — 2026-03-10

- feat: discover OAuth2 collector via DPYC registry (#24)

## [0.7.10] — 2026-03-10

- feat: delegate OAuth2 flow to tollbooth.oauth2_collector (#23)
- feat: use external OAuth collector with npub-as-state (#21) (#21)

## [0.7.8] — 2026-03-09

- fix: forget_credentials clears in-memory state and requires service (#20)
- chore: bump tollbooth-dpyc to >=0.1.83 (#19)

## [0.7.7] — 2026-03-09

- fix: derive OAuth redirect URI at runtime instead of env var (#18)
- chore: bump tollbooth-dpyc to >=0.1.81, version 0.7.6 (#17)
- Drain stale Nostr relay DMs on forget and receive (#16) (#16)

## [0.7.4] — 2026-03-09

- Remove legacy client_id/client_secret fallback from operator callback (#15)

## [0.7.3] — 2026-03-09

- Accept legacy client_id/client_secret keys in operator credential callback (#14)

## [0.7.2] — 2026-03-09

- Bump version to 0.7.2 (#13) (#13)
- Fix operator credential cold-start with session binding resolution (#12) (#12)

## [0.7.1] — 2026-03-09

- Bump version to 0.7.1 (#11) (#11)
- Fix operator credential cold-start restore not populating in-memory cache (#10) (#10)

## [0.7.0] — 2026-03-08

- Add OAuth2 Authorization Code flow for patron onboarding (#9) (#9)

## [0.6.0] — 2026-03-08

- Add patron onboarding guide to README (#8)
- Rename operator credential fields to match Schwab UI (app_key / secret) (#7)

## [0.5.1] — 2026-03-08

- Bump version to 0.5.1 (#6)

## [0.5.0] — 2026-03-08

- Release 0.5.0

## [0.4.8] — 2026-03-22

- chore: sync uv.lock
- fix: resolve ruff lint errors blocking CI (unused imports + variables)
- chore: bump version to 0.8.3 for release
- chore: bump tollbooth-dpyc to >=0.1.100 (notarization catalog + remove get_tax_rate)
- chore: bump version to 0.8.2 for release
- chore: bump tollbooth-dpyc to >=0.1.98 (cache migration fix)
- chore: bump tollbooth-dpyc to >=0.1.97 (tranche TTL expiry)
- chore: sync uv.lock
- chore: bump tollbooth-dpyc to >=0.1.96 for pricing model bridge
- chore: bump tollbooth-dpyc to >=0.1.95 for certify_credits rename
- refactor: rename certifier.certify() to certify_credits()
- chore: bump tollbooth-dpyc to >=0.1.94 for rollback tranche expiry
- chore: nudge deploy for tollbooth-dpyc v0.1.93 PyPI release
- feat: add SVG infographic rendering for account_statement_infographic
- chore: bump tollbooth-dpyc to >=0.1.93
- chore: add fastmcp.json for Horizon deployment config
- fix: handle missing package metadata in service_status (#32)
- feat: report version provenance in service_status (#31)
- chore: nudge deploy for tollbooth-dpyc v0.1.92 release
- Merge pull request #30 from lonniev/chore/bump-tollbooth-0.1.92
- chore: bump tollbooth-dpyc to >=0.1.92 for ACL support
- fix: extract operator_proof from model_json instead of separate tool arg (#29)
- feat: wire catalog conformance check, fix stale test, bump to 0.8.1
- add a sample daily report graphic
- feat: add movers, market hours, and instrument search tools (#28)
- Merge pull request #27 from lonniev/docs/cloud-deployment-readme
- docs: reframe setup as cloud deployment via FastMCP Cloud
- Merge pull request #26 from lonniev/docs/readme-polish-apache
- docs: add hero banner image (options risk profile)
- docs: Apache 2.0 license, Oxcart preference, DPYC trademarks, attribution
- Merge pull request #25 from lonniev/feat/orders-transactions-readme
- feat: add order & transaction history endpoints + Getting Started README
- feat: add DPYC Tollbooth banner to session_status responses
- fix: parse option strikes and expirations from OCC symbol
- feat: shorten OAuth authorize URL via TinyURL for human-friendly UX
- fix: persist OAuth credentials + binding in Courier vault for cold-start restore
- fix: persist DPYC identity binding after OAuth session activation
- feat: resolve OAuth callback URL from registry
- chore: bump to v0.7.15 with tollbooth-dpyc >=0.1.87
- chore: bump to v0.7.14 to retrigger Horizon deploy
- fix: use Horizon /mcp/ prefix for OAuth redirect URI
- chore: bump to v0.7.12 for Horizon redeploy
- feat: discover OAuth2 collector via DPYC registry (#24)
- feat: delegate OAuth2 flow to tollbooth.oauth2_collector (#23)
- feat: use external OAuth collector with npub-as-state (#21) (#21)
- fix: forget_credentials clears in-memory state and requires service (#20)
- chore: bump tollbooth-dpyc to >=0.1.83 (#19)
- fix: derive OAuth redirect URI at runtime instead of env var (#18)
- chore: bump tollbooth-dpyc to >=0.1.81, version 0.7.6 (#17)
- Drain stale Nostr relay DMs on forget and receive (#16) (#16)
- Remove legacy client_id/client_secret fallback from operator callback (#15)
- Accept legacy client_id/client_secret keys in operator credential callback (#14)
- Bump version to 0.7.2 (#13) (#13)
- Fix operator credential cold-start with session binding resolution (#12) (#12)
- Bump version to 0.7.1 (#11) (#11)
- Fix operator credential cold-start restore not populating in-memory cache (#10) (#10)
- Add OAuth2 Authorization Code flow for patron onboarding (#9) (#9)
- Add patron onboarding guide to README (#8)
- Rename operator credential fields to match Schwab UI (app_key / secret) (#7)
- Bump version to 0.5.1 (#6)
- Deliver all Schwab credentials via Secure Courier, remove env vars (#5)

## [0.4.0] — 2026-03-08

- Bump version to 0.4.0
- Update README for v0.3.0: multi-tenant, direct httpx, Tollbooth DPYC
- Remove schwab-py, replace with direct httpx calls (#4)
- Merge pull request #3 from lonniev/chore/env-example
- Add .env.example with all Horizon deployment vars

## [0.3.0] — 2026-03-08

- Merge pull request #2 from lonniev/feature/multi-tenant-tollbooth
- Fix lint: import sorting, line length, unused imports
- Multi-tenant Secure Courier + Tollbooth DPYC integration

## [0.2.0] — 2026-03-08

- Merge pull request #1 from lonniev/feature/streamable-http-async
- Add README with setup, tools, and project structure
- Switch to Streamable HTTP transport with async schwab-py client
- Gracefully handle missing Schwab credentials at startup
- Add .mcp.json to gitignore
- Initial scaffold: FastMCP server, OAuth module, tools, and tests

