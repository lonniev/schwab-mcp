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
| `request_credential_channel` | Open a Secure Courier channel for credential delivery via Nostr DM |
| `receive_credentials` | Pick up credentials from the encrypted vault |
| `forget_credentials` | Delete vaulted credentials for re-delivery |
| `check_balance` | View credit balance and usage |
| `purchase_credits` | Create a Lightning invoice to buy credits |
| `check_payment` | Verify Lightning payment and credit the balance |

All brokerage tools are read-only. No orders are placed.

## Architecture

- **Multi-tenant**: operator delivers `client_id` / `client_secret` via Secure Courier (`service="schwab-operator"`); each user delivers `token_json` + `account_hash` via Secure Courier (`service="schwab"`). No Schwab credentials in env vars
- **Direct httpx**: thin `SchwabClient` wrapper with bearer auth and proactive token refresh (no third-party Schwab SDK)
- **Tollbooth DPYC**: pre-funded Lightning balances, Authority-certified purchase orders, NeonVault (Postgres) for ledger persistence

## Setup

### Prerequisites

- Python 3.11+
- A [Schwab Developer](https://developer.schwab.com/) app with API credentials
- An OAuth token (generated via Schwab's developer portal)

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

50 tests covering all tools, the httpx client, vault, auth, server credit gating, and Secure Courier callbacks.

## Project Structure

```
schwab-mcp/
  server.py            # FastMCP server, singletons, credit gating, 12 tool endpoints
  schwab_client.py     # Thin async httpx client — bearer auth + token refresh
  vault.py             # Per-user session management (in-memory cache)
  auth.py              # CLI bootstrap message (credentials via Secure Courier)
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
