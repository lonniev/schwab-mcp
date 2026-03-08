"""Market data tools — quotes and price history."""

from schwab_client import SchwabClient


async def get_quote(client: SchwabClient, symbols: str) -> str:
    """Get real-time quotes for one or more symbols.

    Args:
        symbols: Comma-separated ticker symbols (e.g. "AAPL,MSFT").
    """
    symbol_list = [s.strip().upper() for s in symbols.split(",")]

    data = await client.get_quotes(symbol_list)

    lines: list[str] = []
    for sym in symbol_list:
        q = data.get(sym, {})
        ref = q.get("reference", {})
        quote_data = q.get("quote", {})
        regular = q.get("regular", {})

        last = quote_data.get("lastPrice", regular.get("lastPrice", 0.0))
        bid = quote_data.get("bidPrice", 0.0)
        ask = quote_data.get("askPrice", 0.0)
        volume = quote_data.get("totalVolume", 0)
        change_pct = quote_data.get("netPercentChange", 0.0)
        high_52 = quote_data.get("52WeekHigh", ref.get("highPrice52", 0.0))
        low_52 = quote_data.get("52WeekLow", ref.get("lowPrice52", 0.0))

        lines.append(
            f"**{sym}** | Last: ${last:.2f} | Bid: ${bid:.2f} / Ask: ${ask:.2f} | "
            f"Vol: {volume:,} | Chg: {change_pct:+.2f}% | "
            f"52wk: ${low_52:.2f} - ${high_52:.2f}"
        )

    return "\n".join(lines)


async def get_price_history(
    client: SchwabClient,
    symbol: str,
    period_type: str = "month",
    period: int = 1,
    frequency_type: str = "daily",
    frequency: int = 1,
) -> str:
    """Get historical OHLCV candle data for a symbol.

    Args:
        symbol: Ticker symbol.
        period_type: "day", "month", "year", or "ytd".
        period: Number of periods.
        frequency_type: "minute", "daily", "weekly", or "monthly".
        frequency: Frequency interval.
    """
    data = await client.get_price_history(
        symbol.upper(),
        periodType=period_type,
        frequencyType=frequency_type,
    )

    candles = data.get("candles", [])
    if not candles:
        return f"No price history available for {symbol.upper()}."

    lines = [f"**{symbol.upper()} Price History** ({len(candles)} candles)\n"]
    lines.append("| Date | Open | High | Low | Close | Volume |")
    lines.append("|------|------|------|-----|-------|--------|")

    for c in candles[-30:]:  # Last 30 candles to keep output manageable
        from datetime import datetime

        dt = datetime.fromtimestamp(c["datetime"] / 1000).strftime("%Y-%m-%d")
        lines.append(
            f"| {dt} | ${c['open']:.2f} | ${c['high']:.2f} | "
            f"${c['low']:.2f} | ${c['close']:.2f} | {c['volume']:,} |"
        )

    if len(candles) > 30:
        lines.append(f"\n_Showing last 30 of {len(candles)} candles._")

    return "\n".join(lines)
