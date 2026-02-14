"""Schwab MCP Server — read-only brokerage data for Claude.ai."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastmcp import Context, FastMCP

from auth import create_client
from config import get_schwab_account_hash
from tools.account import get_account_balances as _get_account_balances
from tools.account import get_positions as _get_positions
from tools.market import get_price_history as _get_price_history
from tools.market import get_quote as _get_quote
from tools.options import get_option_chain as _get_option_chain


@asynccontextmanager
async def app_lifespan(server: FastMCP) -> AsyncIterator[dict]:
    """Initialize the Schwab client on server startup."""
    client = create_client()
    account_hash = get_schwab_account_hash()
    try:
        yield {"schwab_client": client, "account_hash": account_hash}
    finally:
        pass


mcp = FastMCP("Schwab MCP", lifespan=app_lifespan)


@mcp.tool()
async def get_positions(ctx: Context) -> str:
    """Get current portfolio positions with options spread detection.

    Shows all open positions including equities and options.
    Options positions are automatically paired into spreads where possible,
    displaying credit received, max loss, current value, and P&L.
    """
    client = ctx.lifespan_context["schwab_client"]
    account_hash = ctx.lifespan_context["account_hash"]
    return _get_positions(client, account_hash)


@mcp.tool()
async def get_balances(ctx: Context) -> str:
    """Get account balances: cash, buying power, net liquidation value, and day P&L."""
    client = ctx.lifespan_context["schwab_client"]
    account_hash = ctx.lifespan_context["account_hash"]
    return _get_account_balances(client, account_hash)


@mcp.tool()
async def get_quote(symbols: str, ctx: Context) -> str:
    """Get real-time quotes for one or more symbols.

    Args:
        symbols: Comma-separated ticker symbols (e.g. "AAPL,MSFT,TSLA").
    """
    client = ctx.lifespan_context["schwab_client"]
    return _get_quote(client, symbols)


@mcp.tool()
async def get_option_chain(
    symbol: str,
    ctx: Context,
    strike_count: int = 20,
    contract_type: str = "ALL",
    days_to_expiration: int = 21,
) -> str:
    """Get filtered option chain for spread evaluation.

    Returns contracts filtered by DTE and open interest (>= 25),
    with Greeks, IV, and OTM percentage for efficient spread scanning.

    Args:
        symbol: Underlying ticker symbol.
        strike_count: Number of strikes around ATM to include.
        contract_type: "ALL", "CALL", or "PUT".
        days_to_expiration: Maximum days to expiration to include.
    """
    client = ctx.lifespan_context["schwab_client"]
    return _get_option_chain(client, symbol, strike_count, contract_type, days_to_expiration)


@mcp.tool()
async def get_price_history(
    symbol: str,
    ctx: Context,
    period_type: str = "month",
    period: int = 1,
    frequency_type: str = "daily",
    frequency: int = 1,
) -> str:
    """Get historical OHLCV price data for trend analysis.

    Args:
        symbol: Ticker symbol.
        period_type: "day", "month", "year", or "ytd".
        period: Number of periods.
        frequency_type: "minute", "daily", "weekly", or "monthly".
        frequency: Frequency interval.
    """
    client = ctx.lifespan_context["schwab_client"]
    return _get_price_history(client, symbol, period_type, period, frequency_type, frequency)


if __name__ == "__main__":
    mcp.run()
