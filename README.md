# schwab-mcp

![Open Positions — Options Risk Profile](assets/hero-banner.png)

**Your brokerage data, conversationally.** Ask your AI assistant about your positions, screen option spreads, audit today's trades against your strategy rules, and get end-of-day reports — all from natural language. The data cost? About 6 sats per session (~$0.005).

## Why This Exists

The data in schwab-mcp is nothing you can't get from ThinkOrSwim, OptionAlpha, or Schwab's own web UI. What you *can't* get from those tools is a **personal trading assistant** that blends:

- Your live positions and account balances
- Real-time option chains with Greeks, IV, and OTM%
- Your trading strategy rules (credit floors, RWR targets, sector concentration limits)
- Market context (earnings calendars, VIX levels, sector rotation)
- All of the above in a single conversational turn

Ask *"How would you judge my new trades for the day?"* and get a structured audit against your criteria. Ask *"What are three SPS candidates aligned with my strategy and balanced with my current book?"* and get sector-aware, earnings-aware, IV-aware suggestions — grounded in your actual positions, not generic advice.

The AI does the synthesis. schwab-mcp provides the data bridge. You pay per-call in Bitcoin Lightning sats — no subscription, no KYC, no vendor lock-in. A full day of morning report + evening report + follow-up analysis costs about **6 sats** (< $0.01).

---

Multi-tenant [MCP](https://modelcontextprotocol.io/) server exposing Charles Schwab brokerage data to AI agents via [FastMCP](https://github.com/jlowin/fastmcp). Monetized via [Tollbooth DPYC](https://github.com/lonniev/tollbooth-dpyc)&trade; Lightning micropayments. Serves over **Streamable HTTP** with direct async httpx calls to `api.schwabapi.com`.

> Don't Pester Your Customer&trade; (DPYC&trade;) &mdash; API monetization for Entrepreneurial Bitcoin Advocates

*Inspired by [The Phantom Tollbooth](https://en.wikipedia.org/wiki/The_Phantom_Tollbooth) by Norton Juster, illustrated by Jules Feiffer (1961).*

**Version:** 0.10.0 &nbsp; ![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue)

## The DPYC&trade; Economy

**DPYC&trade;** stands for **Don't Pester Your Customer**. It is a philosophy and
protocol for API monetization that eliminates mid-session payment popups,
subscription nag screens, and KYC friction.

### How it works

1. **Pre-funded balances** -- Users buy credits (api_sats) via Bitcoin Lightning
   *before* using tools. Each tool call silently debits from their balance. No
   interruptions, no "please upgrade" modals. Credits expire after a
   `tranche_lifetime` window set by the operator's pricing model.

2. **Nostr keypair identity** -- Users are identified by a Nostr public key
   (`npub`), not an email or password. One keypair per role, managed by the
   user. No account creation forms.

3. **Poison-keyed proof** -- Every paid tool call requires a `proof`
   parameter carrying a poison phrase (e.g., `bold-hawk-42`) returned by
   `request_npub_proof` / `receive_npub_proof`. The calling application
   remembers this token and passes it on every subsequent call. The MCP
   stores only `sha256(poison):npub` in the vault -- never the raw phrase.
   Proofs are generated via a **human-in-the-loop** Secure Courier exchange:
   the patron consciously approves each proof request in their Nostr client.
   Duration is patron-chosen (up to 7 days). Proofs survive MCP restarts.

4. **UUID-keyed tool identity** -- Every tool is a `ToolIdentity` object with
   a deterministic UUID v5 derived from a capability name. Pricing hints come
   from the `category` field:

   | Category | Pricing hint | Use case                    |
   |----------|--------------|-----------------------------|
   | `free`   | 0 sats       | Balance checks, status      |
   | `read`   | 1 sat        | Simple lookups              |
   | `write`  | 5 sats       | Multi-step operations       |
   | `heavy`  | 10 sats      | Expensive queries           |

   Actual prices (api_sats) are set dynamically by the operator's pricing model
   in Neon.

5. **Rollback on failure** -- If the downstream API fails after a debit,
   credits are automatically rolled back via a compensating tranche. The
   user never pays for a failed call.

6. **Honor Chain** -- The DPYC&trade; ecosystem is a voluntary community:
   - **Citizens** -- Users who consume API services
   - **Operators** -- Developers who run MCP services (like this one)
   - **Authorities** -- Certify operators and collect a small tax on purchases
   - **First Curator** -- The root of the chain, mints the initial cert-sat supply

## Tools

### Brokerage (paid -- credit-gated)

All paid tools require `npub` and `proof` parameters for identity verification.

| Tool | Tier | Description |
|------|------|-------------|
| `get_brokerage_positions` | write | Portfolio positions with automatic options spread detection (bull put / bear call) |
| `get_brokerage_balances` | write | Cash, buying power, net liquidation value, day P&L |
| `get_stock_quote` | write | Real-time quotes for one or more symbols |
| `get_market_movers` | write | Top movers for a market index ($SPX, $DJI, $COMPX) |
| `get_market_hours` | write | Trading hours for equity, option, bond, future, forex markets |
| `search_instruments` | write | Search for instruments by symbol, name, or CUSIP |
| `get_option_chain` | heavy | Filtered option chain with Greeks, IV, OTM%, and OI threshold |
| `get_price_history` | heavy | Historical OHLCV candle data |
| `get_brokerage_orders` | heavy | Order history with multi-leg spread support (default 30 days) |
| `get_brokerage_order` | heavy | Single order detail by ID |
| `get_brokerage_transactions` | heavy | Transaction history -- trades, dividends, cash movements (default 30 days) |
| `get_brokerage_transaction` | heavy | Single transaction detail by ID |

### Free

| Tool | Description |
|------|-------------|
| `session_status` | Check operator lifecycle state and readiness |
| `service_status` | Check health and configuration of this service |
| `begin_oauth` | Start OAuth2 flow -- returns Schwab authorization URL |
| `check_oauth_status` | Poll whether OAuth flow completed and session is active |
| `get_account_numbers` | List linked Schwab account numbers and hashes |
| `request_credential_channel` | Open a Secure Courier channel for credential delivery via Nostr DM |
| `receive_credentials` | Pick up credentials from the encrypted vault |
| `forget_credentials` | Delete vaulted credentials for re-delivery |
| `update_patron_credential` | Add or update a single patron credential field |
| `delete_patron_credential` | Remove a single patron credential field |
| `get_patron_credential_fields` | List stored patron credential field names |
| `check_balance` | View credit balance and usage |
| `check_price` | Preview tool cost before calling |
| `purchase_credits` | Create a Lightning invoice to buy credits |
| `check_payment` | Verify Lightning payment and credit the balance |
| `restore_credits` | Restore credits from a previously paid invoice |
| `account_statement` | View account statement summary |
| `account_statement_infographic` | Visual SVG infographic of account (1 sat) |
| `check_authority_balance` | Check operator's cert-sat balance at Authority |
| `get_pricing_model` | View the active pricing model |
| `list_constraint_types` | List available constraint types and schemas |
| `request_npub_proof` | Request poison-keyed ownership proof via Nostr DM |
| `receive_npub_proof` | Receive and cache proof; returns proof_token |
| `get_operator_onboarding_status` | Report operator configuration readiness |
| `get_patron_onboarding_status` | Report patron credential readiness |
| `list_notarizations` | List recent Bitcoin notarization records |
| `get_notarization_proof` | Generate a Merkle inclusion proof for a patron balance |

All brokerage tools are read-only. No orders are placed.

## Architecture

- **Multi-tenant**: operator delivers `btcpay_host` + `btcpay_api_key` + `btcpay_store_id` + `app_key` + `secret` via Secure Courier (`service="schwab-operator"`); each patron authenticates via OAuth2 browser flow. Sessions are keyed by npub. No Schwab credentials in env vars
- **Direct httpx**: thin `SchwabClient` wrapper with bearer auth and proactive token refresh (no third-party Schwab SDK)
- **Tollbooth DPYC&trade;**: pre-funded Lightning balances, Authority-certified purchase orders, NeonVault (Postgres) for ledger persistence
- **Registry discovery**: OAuth2 collector URL resolved from DPYC&trade; registry at runtime (no `OAUTH_COLLECTOR_URL` env var needed)
- **Credential validation**: operator credentials are validated at receive time -- `btcpay_host`, `app_key`, and `secret` must all be present before vaulting
- **Poison-keyed proof**: all paid tools require a `proof` parameter -- a poison phrase from `request_npub_proof` / `receive_npub_proof` that the calling application remembers. The MCP stores only the hash. Survives restarts; patron-chosen TTL up to 7 days. Restricted tools (operator-only) still use kind-27235 Schnorr signatures.

---

## Getting Started

This guide covers the full Tollbooth onboarding path -- from generating a Nostr identity to making your first brokerage data call. It applies to both **Operators** (who deploy schwab-mcp) and **Patrons** (who consume it through Claude.ai or another MCP client).

### 1. Get a Nostr Identity (npub)

Every participant in the DPYC&trade; ecosystem is identified by a **Nostr keypair** -- no email, no password, no vendor lock-in.

**What is an npub?** It is a public key in the [Nostr protocol](https://nostr.com/), encoded as a bech32 string starting with `npub1...`. Your corresponding private key (`nsec1...`) stays on your device. The npub is safe to share -- it is how the system knows who you are.

**How to generate one:**

1. Install [Oxcart](https://github.com/nickkawai/Oxcart) (the preferred Nostr client for DPYC&trade; workflows; other clients have not been tested)
2. Create an account -- the app generates your keypair automatically
3. Find your npub in the app's profile/settings screen (it starts with `npub1...`)

Alternatively, use a CLI key generator like [nak](https://github.com/fiatjaf/nak): `nak key generate`

**Operators** should keep a separate npub for their service identity, distinct from their personal Nostr account.

### 2. Register as a DPYC&trade; Citizen

Before you can buy credits or operate a service, register your npub with the DPYC&trade; community:

1. In Claude.ai (with the [DPYC Oracle](https://github.com/lonniev/dpyc-oracle) connected), call `how_to_join()` to learn about citizenship
2. Follow the Oracle's instructions to register your npub

Citizenship is free and gives you a portable identity across the entire Tollbooth network.

### 3. For Operators -- Set Up Your BTCPay Store

The Operator collects Lightning payments from Patrons via [BTCPay Server](https://btcpayserver.org/). You need:

- A BTCPay Server instance (self-hosted or hosted by your Authority)
- A **Store ID** and **API Key** with invoice creation permissions

These credentials are delivered via Secure Courier (see step 6), not set as environment variables.

### 4. For Operators -- Register with a Tollbooth Authority

Every Operator is sponsored by an Authority in the DPYC&trade; trust chain. The Authority certifies your purchase orders and collects a small fee (default 2%).

1. Connect to your Authority's MCP service (e.g., [tollbooth-authority](https://github.com/lonniev/tollbooth-authority))
2. Call `register_operator(npub=<your_operator_npub>)` -- creates your ledger entry
3. The Authority approves your registration

### 5. For Operators -- Fund Your Certification Balance

Before your service can issue credits to Patrons, you need cert-sats:

1. Call `authority_purchase_credits(amount_sats=1000)` on your Authority -- returns a Lightning invoice
2. Pay the invoice with any Lightning wallet
3. Call `authority_check_payment(invoice_id="...")` -- confirms settlement and credits your balance

Your cert-sat balance is consumed automatically when Patrons purchase credits from your service.

### 6. For Operators -- Deliver Credentials (Secure Courier)

The Operator must register a [Schwab Developer](https://developer.schwab.com/) app and deliver both BTCPay and Schwab API credentials via Secure Courier. Credentials **never appear in chat**.

Schwab Developer apps use `app_key` and `secret` as the vendor field names (these map to OAuth `client_id` and `client_secret` internally). The `redirect_uri` registered with Schwab should have **no `/callback` suffix** -- use the base collector URL exactly as shown in the registry.

The Secure Courier is a **human-in-the-loop** exchange: the operator consciously replies in their Nostr client. The relay is drained destructively after pickup -- messages are consumed, not left on the wire.

1. Call `request_credential_channel(service="schwab-operator", recipient_npub=<operator_npub>)` -- a welcome DM arrives in your Nostr client ([Oxcart](https://github.com/nickkawai/Oxcart))
2. In Oxcart, reply to the DM with:
   ```json
   {
     "btcpay_host": "https://btcpay.example.com",
     "btcpay_api_key": "YOUR_API_KEY",
     "btcpay_store_id": "YOUR_STORE_ID",
     "app_key": "YOUR_SCHWAB_APP_KEY",
     "secret": "YOUR_SCHWAB_SECRET"
   }
   ```
3. Call `receive_credentials(sender_npub=<operator_npub>, service="schwab-operator")` -- credentials are validated (`btcpay_host`, `app_key`, and `secret` must all be present) and vaulted

This is a one-time setup per deployment. Operator credentials are encrypted and stored in the NeonVault, persisting across server restarts.

### 7. For Patrons -- Buy Credits (api_sats)

Patrons pre-fund a satoshi balance and consume brokerage tools against it -- no per-request payment interruptions. This is the Don't Pester Your Customer&trade; philosophy in action. Credits are denominated in **api_sats** and expire after the operator-configured `tranche_lifetime`.

1. Call `purchase_credits(amount_sats=500)` -- returns a Lightning invoice with a checkout link
2. Pay the invoice with any Lightning wallet (Phoenix, Breez, Zeus, etc.)
3. Call `check_payment(invoice_id="...")` -- confirms settlement and credits your balance

Your balance depletes as you call paid tools. Recharge anytime with another `purchase_credits` call. Check your balance at any time with `check_balance` (free). Preview any tool's cost with `check_price` (free).

### 8. For Patrons -- Connect Your Schwab Account

You need to authorize schwab-mcp to read your Schwab account. Choose one method:

### Patron Onboarding

1. Call `begin_oauth(npub=<your_npub>)` to get an authorization URL
2. Open the URL in your browser and log in to Schwab
3. Call `check_oauth_status(npub=<your_npub>)` to confirm session activation
4. Call `get_account_numbers(npub=<your_npub>)` to list your accounts and hashes
5. Call `update_patron_credential(npub=<your_npub>, field="account_hash", value=<hash>)` to set your preferred account

### 9. Using Schwab Tools in Conversation

Once your session is active, ask your AI agent naturally:

- *"Show me my positions"* -- calls `get_brokerage_positions`
- *"What's my account balance?"* -- calls `get_brokerage_balances`
- *"Get a quote for AAPL and MSFT"* -- calls `get_stock_quote`
- *"What are today's biggest gainers?"* -- calls `get_market_movers`
- *"Is the market open tomorrow?"* -- calls `get_market_hours`
- *"Look up the ticker for Berkshire Hathaway"* -- calls `search_instruments`
- *"Show me the GLD option chain for next month"* -- calls `get_option_chain`
- *"What are my recent orders?"* -- calls `get_brokerage_orders`
- *"Show me my trade history for the last week"* -- calls `get_brokerage_transactions`

Free tools are always available:

- *"What's my schwab-mcp balance?"* -- calls `check_balance`
- *"Show me my account statement"* -- calls `account_statement`

---

## Security

- **npub identity** -- All sessions are keyed by a Nostr public key. No email, no username, no password.
- **kind-27235 Schnorr proof** -- Every paid tool call requires a cryptographic proof that the caller controls the claimed npub. Proofs are requested and delivered via Secure Courier with human-in-the-loop approval.
- **Secure Courier** -- Credentials are exchanged over NIP-04 encrypted Nostr DMs. The relay is drained destructively after pickup; messages do not persist on the wire.
- **NeonVault** -- Credentials (`token_json`) and ledger state are stored in Postgres with per-operator row isolation. No secrets in environment variables or chat history.
- **Operator credential isolation** -- BTCPay and Schwab API credentials (`app_key`, `secret`) are delivered via Secure Courier with `service="schwab-operator"`, validated at receive time, and never exposed in logs or responses.

## Troubleshooting

**Cold start / first tool call fails:** The FastMCP Cloud runtime may cold-start on the first request. Retry the tool call inline -- the server warms up within a few seconds and the second call succeeds.

**"proof is required":** Call `request_npub_proof` followed by `receive_npub_proof` to prove npub ownership. The response includes a `proof_token` -- pass it as the `proof` parameter on every subsequent paid tool call. Duration is patron-chosen (up to 7 days). The proof survives MCP restarts.

**"Insufficient credit balance":** Call `purchase_credits` to top up. Use `check_balance` to see your current api_sats balance and `tranche_lifetime` expiry.

**"Operator credentials not configured":** This is an operator setup issue, not the patron's problem. The operator must complete the Secure Courier flow (step 6) to deliver `app_key` and `secret`.

**Credential lifecycle states:** Credentials move through `pending` (channel opened) -> `delivered` (DM sent by human) -> `vaulted` (picked up and validated). If `receive_credentials` returns a lifecycle state instead of success, it is not an error -- it is telling you where in the flow you are. Follow the guidance in the response.

**OAuth token stored in vault:** After a successful OAuth2 flow, the `token_json` is persisted in NeonVault. Sessions survive server restarts via the wheel's `restore_oauth_session` -- which detects expiration, refreshes the token via the provider, and persists the rotated pair back to vault. If the refresh token itself expires (Schwab: 7 days), the patron must re-run `begin_oauth`.

---

## DPYC&trade; Community Resources

| Resource | Description |
|----------|-------------|
| [dpyc-community](https://github.com/lonniev/dpyc-community) | Community registry, governance, creed, and trademarks |
| [tollbooth-dpyc](https://github.com/lonniev/tollbooth-dpyc) | Operator SDK -- Python library for Tollbooth DPYC&trade; monetization |
| [tollbooth-authority](https://github.com/lonniev/tollbooth-authority) | Authority MCP service -- fee collection, Schnorr signing, purchase order certification |
| [thebrain-mcp](https://github.com/lonniev/thebrain-mcp) | Personal Brain MCP service -- the first city on the Lightning Turnpike |
| [excalibur-mcp](https://github.com/lonniev/excalibur-mcp) | X (Twitter) posting service with Secure Courier |
| [dpyc-oracle](https://github.com/lonniev/dpyc-oracle) | Community concierge -- free membership, governance, and onboarding tools |
| [DPYC Whitepaper](https://github.com/lonniev/dpyc-community/blob/main/docs/WHITEPAPER.md) | Technical whitepaper for the Tollbooth architecture |
| [The Phantom Tollbooth on the Lightning Turnpike](https://stablecoin.myshopify.com/blogs/our-value/the-phantom-tollbooth-on-the-lightning-turnpike) | Narrative introduction to Tollbooth DPYC&trade; |

---

## Deployment

schwab-mcp runs on [FastMCP Cloud](https://www.fastmcp.cloud/). Any MCP client (Claude.ai, Claude Desktop, Cursor, your own agent) can connect:

```
https://www.fastmcp.cloud/server/lonniev/schwab-mcp
```

Patron identity is established via the OAuth2 flow (`begin_oauth` / `check_oauth_status`) or Secure Courier. Sessions are keyed by npub.

### Operator Environment Variables

#### Required

| Variable | Description |
|----------|-------------|
| `TOLLBOOTH_NOSTR_OPERATOR_NSEC` | Operator's Nostr secret key -- the single bootstrap key for identity, Secure Courier DMs, and audit signing |

This is the only env var required to start. Certified operators bootstrap their Neon database URL from the Authority via encrypted Nostr DM -- `NEON_DATABASE_URL` is not read from the environment.

#### Optional Tuning

| Variable | Description |
|----------|-------------|
| `TOLLBOOTH_NOSTR_RELAYS` | Comma-separated relay URLs (overrides defaults) |
| `SCHWAB_TRADER_API` | API base URL (default `https://api.schwabapi.com`) |
| `CREDIT_TTL_SECONDS` | Fallback tranche lifetime in seconds (default: 604800 = 7 days). Overridden by `tranche_lifetime.ttl_days` in the pricing model if set. |
| `DPYC_REGISTRY_CACHE_TTL_SECONDS` | How long to cache the DPYC community registry (default: 300) |

#### Credentials via Secure Courier (NOT env vars)

BTCPay credentials (`btcpay_host`, `btcpay_api_key`, `btcpay_store_id`) and Schwab API credentials (`app_key`, `secret`) are delivered exclusively through Secure Courier (`service="schwab-operator"`), validated at receive time, and stored in the encrypted vault. No secrets in env vars or chat.

## Development

### Prerequisites

- Python 3.12+
- A [Schwab Developer](https://developer.schwab.com/) app with API credentials
- [Oxcart](https://github.com/nickkawai/Oxcart) Nostr client for Secure Courier credential delivery

### Install & Test

```bash
uv sync            # or: pip install -e ".[dev]"
uv run pytest tests/ -v
```

## Project Structure

```
schwab-mcp/
  server.py            # FastMCP server, OperatorRuntime, credit gating, domain tool endpoints
  schwab_client.py     # Thin async httpx client — bearer auth + token refresh
  vault.py             # Per-user session management (in-memory cache)
  oauth_flow.py        # OAuth2 authorization code flow (state tokens, exchange, callback)
  settings.py          # pydantic-settings (env vars, .env file)
  models.py            # Pydantic response models
  tools/
    account.py         # Positions, balances, orders, transactions (spread detection)
    market.py          # Quotes, price history, market movers, market hours, instrument search
    options.py         # Option chain retrieval + filtering
  tests/
    test_schwab_client.py  # httpx client, token refresh, URL building
    test_server.py         # Singletons, credit gating, Secure Courier callback
    test_vault.py          # Session management
    test_account.py        # Position, balance, order, transaction parsing
    test_market.py         # Quote + price history formatting
    test_options.py        # Option chain filtering
```

## Prior Art & Attribution

The methods, algorithms, and implementations contained in this repository may represent original work by Lonnie VanZandt, first published in April 2026. This public disclosure establishes prior art under U.S. patent law (35 U.S.C. 102).

All use, reproduction, or derivative work must comply with the Apache License 2.0 included in this repository and must provide proper attribution to the original author per the [NOTICE](NOTICE) file.

### How to Attribute

If you use or build upon this work, please include the following in your documentation or source:

    Based on original work by Lonnie VanZandt and Claude.ai
    Originally published: April 2026
    Source: https://github.com/lonniev/schwab-mcp
    Licensed under Apache License 2.0

Visit the technologist's virtual cafe for Bitcoin advocates and coffee aficionados at [stablecoin.myshopify.com](https://stablecoin.myshopify.com).

### Patent Notice

The author reserves all rights to seek patent protection for the novel methods and systems described herein. Public disclosure of this work establishes a priority date of April 2026. Under the America Invents Act, the author retains a one-year grace period from the date of first public disclosure to file patent applications.

**Note to potential filers:** This public repository and its full Git history serve as evidence of prior art. Any patent application covering substantially similar methods filed after the publication date of this repository may be subject to invalidation under 35 U.S.C. 102(a).

## Further Reading

[The Phantom Tollbooth on the Lightning Turnpike](https://stablecoin.myshopify.com/blogs/our-value/the-phantom-tollbooth-on-the-lightning-turnpike) -- the full story of how we're monetizing the monetization of AI APIs, and then fading to the background.

## Trademarks

DPYC&trade;, Tollbooth DPYC&trade;, and Don't Pester Your Customer&trade; are trademarks of Lonnie VanZandt. See the [TRADEMARKS.md](https://github.com/lonniev/dpyc-community/blob/main/TRADEMARKS.md) in the dpyc-community repository for usage guidelines.

## License

Apache License 2.0 -- see [LICENSE](LICENSE) and [NOTICE](NOTICE) for details.

---

*Because in the end, the tollbooth was never the destination. It was always just the beginning of the journey.*
