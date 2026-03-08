# schwab-mcp

Read-only [MCP](https://modelcontextprotocol.io/) server exposing Charles Schwab brokerage data to AI agents via [FastMCP](https://github.com/jlowin/fastmcp). Serves over **Streamable HTTP** with an async schwab-py client so it can run as a long-lived HTTP server without blocking on Schwab API calls.

## Tools

| Tool | Description |
|------|-------------|
| `get_positions` | Portfolio positions with automatic options spread detection (bull put / bear call) |
| `get_balances` | Cash, buying power, net liquidation value, day P&L |
| `get_quote` | Real-time quotes for one or more symbols |
| `get_option_chain` | Filtered option chain with Greeks, IV, OTM%, and OI threshold |
| `get_price_history` | Historical OHLCV candle data |

All tools are read-only. No orders are placed.

## Setup

### Prerequisites

- Python 3.11+
- A [Schwab Developer](https://developer.schwab.com/) app with API credentials
- An OAuth token obtained via the bootstrap flow

### Install

```bash
uv sync            # or: pip install -e ".[dev]"
```

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `SCHWAB_CLIENT_ID` | Yes | Schwab API app key |
| `SCHWAB_CLIENT_SECRET` | Yes | Schwab API app secret |
| `SCHWAB_TOKEN_JSON` | Yes | JSON string of the OAuth token (from bootstrap) |
| `SCHWAB_ACCOUNT_HASH` | Yes | Account hash (from Schwab account numbers endpoint) |
| `SCHWAB_MCP_HOST` | No | Bind address (default `127.0.0.1`) |
| `SCHWAB_MCP_PORT` | No | Bind port (default `8000`) |

### Bootstrap Token

```bash
python auth.py bootstrap
```

This opens a browser for Schwab OAuth login, writes `token.json`, and prints the JSON to paste into `SCHWAB_TOKEN_JSON`. Refresh tokens expire after 7 days — re-bootstrap before then.

## Run

```bash
python server.py
```

The server binds to `127.0.0.1:8000` by default and serves MCP over Streamable HTTP.

### Verify

```bash
curl http://127.0.0.1:8000/mcp
```

### Graceful Degradation

If Schwab credentials are missing, the server starts normally but all tools return a descriptive error message prompting the operator to configure environment variables.

## Tests

```bash
uv run pytest tests/ -v
```

17 tests covering all tools with mocked Schwab API responses.

## Project Structure

```
schwab-mcp/
  server.py          # FastMCP server, lifespan, tool wrappers
  auth.py            # OAuth token management + bootstrap CLI
  config.py          # Environment variable accessors
  models.py          # Pydantic response models
  tools/
    account.py       # Positions + balances (spread detection)
    market.py        # Quotes + price history
    options.py       # Option chain retrieval + filtering
  tests/
    test_auth.py
    test_account.py
    test_market.py
    test_options.py
```

## License

MIT
