# schwab-mcp

Multi-tenant [MCP](https://modelcontextprotocol.io/) server exposing Charles Schwab brokerage data to AI agents via [FastMCP](https://github.com/jlowin/fastmcp). Monetized via [DPYC Tollbooth](https://github.com/lonniev/tollbooth-dpyc) Lightning micropayments. Serves over **Streamable HTTP** with direct async httpx calls to `api.schwabapi.com`.

## Tools

### Brokerage (paid — credit-gated)

| Tool | Cost | Description |
|------|------|-------------|
| `get_positions` | 5 api_sats | Portfolio positions with automatic options spread detection (bull put / bear call) |
| `get_balances` | 5 api_sats | Cash, buying power, net liquidation value, day P&L |
| `get_quote` | 5 api_sats | Real-time quotes for one or more symbols |
| `get_option_chain` | 10 api_sats | Filtered option chain with Greeks, IV, OTM%, and OI threshold |
| `get_price_history` | 10 api_sats | Historical OHLCV candle data |

### Free

| Tool | Description |
|------|-------------|
| `session_status` | Check current session and DPYC identity state |
| `begin_oauth` | Start OAuth2 flow — returns Schwab authorization URL |
| `check_oauth_status` | Poll whether OAuth flow completed and session is active |
| `request_credential_channel` | Open a Secure Courier channel for credential delivery via Nostr DM |
| `receive_credentials` | Pick up credentials from the encrypted vault |
| `forget_credentials` | Delete vaulted credentials for re-delivery |
| `check_balance` | View credit balance and usage |
| `purchase_credits` | Create a Lightning invoice to buy credits |
| `check_payment` | Verify Lightning payment and credit the balance |

All brokerage tools are read-only. No orders are placed.

## Architecture

- **Multi-tenant**: operator delivers `app_key` / `secret` via Secure Courier (`service="schwab-operator"`); each user delivers `token_json` + `account_hash` via Secure Courier (`service="schwab"`). No Schwab credentials in env vars
- **Direct httpx**: thin `SchwabClient` wrapper with bearer auth and proactive token refresh (no third-party Schwab SDK)
- **Tollbooth DPYC**: pre-funded Lightning balances, Authority-certified purchase orders, NeonVault (Postgres) for ledger persistence
- **Registry discovery**: OAuth2 collector URL resolved from DPYC registry at runtime (no `OAUTH_COLLECTOR_URL` env var needed)

## Patron Onboarding — Getting Your Schwab Credentials

Two credentials are needed to activate a patron session: `token_json` (the full OAuth token) and `account_hash` (Schwab's encrypted account identifier).

### Option A — OAuth Flow (recommended)

The server handles the token exchange and session activation automatically:

1. In your MCP client, call `begin_oauth(patron_npub=<your_npub>)` — returns a Schwab authorization URL
2. Open the URL in your browser and log in to Schwab
3. Schwab redirects back to the server — token exchange and account lookup happen automatically
4. Call `check_oauth_status()` to confirm your session is active

No curl commands, no copy-paste. Your credentials never appear in the chat.

### Option B — Manual Secure Courier

If the OAuth redirect is unreachable (e.g. firewalled local dev), you can deliver credentials manually:

#### Step 1 — Authorization URL

Open in your browser (substitute your App Key):

```
https://api.schwabapi.com/v1/oauth/authorize?response_type=code&client_id=YOUR_APP_KEY&scope=readonly&redirect_uri=https://127.0.0.1
```

Log in to Schwab and authorize. The browser redirects to an unreachable page — this is expected. Copy the `code` parameter from the URL bar:

```
https://127.0.0.1/?code=LONG_CODE_STRING&session=...
```

#### Step 2 — Token Exchange

Run immediately (the code expires quickly):

```bash
curl -X POST https://api.schwabapi.com/v1/oauth/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -u "YOUR_APP_KEY:YOUR_SECRET" \
  -d "grant_type=authorization_code" \
  -d "code=LONG_CODE_STRING" \
  -d "redirect_uri=https://127.0.0.1"
```

The full JSON response is your `token_json`.

#### Step 3 — Get Account Hash

```bash
curl -X GET https://api.schwabapi.com/trader/v1/accounts/accountNumbers \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

The `hashValue` field is your `account_hash`.

#### Step 4 — Deliver via Secure Courier

In Claude.ai (or your MCP client):

1. Call `request_credential_channel(recipient_npub=<your_npub>)` — a welcome DM arrives in your Nostr client
2. Reply with:
   ```json
   {"token_json": "<paste full token JSON>", "account_hash": "<hashValue>"}
   ```
3. Call `receive_credentials(sender_npub=<your_npub>)` — session activates

Your credentials never appear in the chat. The `refresh_token` in `token_json` auto-renews access (7-day TTL from Schwab).

## Setup

### Prerequisites

- Python 3.11+
- A [Schwab Developer](https://developer.schwab.com/) app with API credentials
- A Nostr client (Primal, Damus, Amethyst, etc.) for Secure Courier credential delivery

### Install

```bash
uv sync            # or: pip install -e ".[dev]"
```

### Environment Variables

See [`.env.example`](.env.example) for the full list. Key variables:

| Variable | Required | Description |
|----------|----------|-------------|
| `SCHWAB_TRADER_API` | No | API base URL (default `https://api.schwabapi.com`) |
| `TOLLBOOTH_NOSTR_OPERATOR_NSEC` | Yes | Nostr signing key for Secure Courier |
| `NEON_DATABASE_URL` | Yes | Postgres for NeonVault (ledger + credential persistence) |
| `BTCPAY_HOST` / `BTCPAY_STORE_ID` / `BTCPAY_API_KEY` | Yes | BTCPay Server for Lightning invoices |

All Schwab credentials flow exclusively through Secure Courier:
- **Operator** delivers `app_key` + `secret` via `service="schwab-operator"` (one-time, mapped internally to client_id/client_secret)
- **Patron** delivers `token_json` + `account_hash` via `service="schwab"` (per-user)

No Schwab secrets ever appear in env vars or chat.

## Run

```bash
python server.py
```

The server binds to `0.0.0.0:8000` and serves MCP over Streamable HTTP.

### Verify

```bash
curl http://localhost:8000/mcp
```

## Tests

```bash
uv run pytest tests/ -v
```

79 tests covering all tools, the httpx client, vault, auth, OAuth flow, server credit gating, registry-based collector discovery, and Secure Courier callbacks.

## Project Structure

```
schwab-mcp/
  server.py            # FastMCP server, singletons, credit gating, 14 tool endpoints
  schwab_client.py     # Thin async httpx client — bearer auth + token refresh
  vault.py             # Per-user session management (in-memory cache)
  auth.py              # CLI bootstrap message (credentials via Secure Courier)
  oauth_flow.py        # OAuth2 authorization code flow (state tokens, exchange, callback)
  settings.py          # pydantic-settings (env vars, .env file)
  models.py            # Pydantic response models
  tools/
    account.py         # Positions + balances (spread detection)
    market.py          # Quotes + price history
    options.py         # Option chain retrieval + filtering
  tests/
    test_schwab_client.py  # httpx client, token refresh, URL building
    test_server.py         # Singletons, credit gating, Secure Courier callback
    test_vault.py          # Session management
    test_auth.py           # Client creation
    test_account.py        # Position + balance parsing
    test_market.py         # Quote + price history formatting
    test_options.py        # Option chain filtering
```

## License

MIT
