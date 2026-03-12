"""Market data tools — quotes, price history, movers, hours, instruments."""

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


async def get_movers(
    client: SchwabClient,
    index: str = "$SPX",
    sort: str = "PERCENT_CHANGE_UP",
    frequency: int = 0,
) -> str:
    """Get top movers for a market index.

    Args:
        index: Index symbol — "$DJI", "$COMPX", or "$SPX".
        sort: "PERCENT_CHANGE_UP", "PERCENT_CHANGE_DOWN", or "VOLUME".
        frequency: 0 = all, 1 = 1–5%, 2 = 5–10%, 3 = 10–20%, 4 = 20%+.
    """
    data = await client.get_movers(index, sort=sort, frequency=frequency)

    screeners = data.get("screeners", [])
    if not screeners:
        return f"No movers found for {index}."

    lines = [f"**{index} Top Movers** ({sort.replace('_', ' ').title()})\n"]
    lines.append("| Symbol | Description | Change % | Volume | Last |")
    lines.append("|--------|-------------|----------|--------|------|")

    for m in screeners[:20]:
        sym = m.get("symbol", "?")
        desc = m.get("description", "")[:30]
        chg = m.get("netPercentChange", 0.0)
        vol = m.get("totalVolume", 0)
        last = m.get("lastPrice", 0.0)
        lines.append(f"| {sym} | {desc} | {chg:+.2f}% | {vol:,} | ${last:.2f} |")

    return "\n".join(lines)


async def get_market_hours(
    client: SchwabClient,
    markets: str = "equity,option",
    date: str | None = None,
) -> str:
    """Get market hours for one or more market types.

    Args:
        markets: Comma-separated: "equity", "option", "bond", "future", "forex".
        date: ISO date to check (e.g. "2026-03-15"). Defaults to today.
    """
    data = await client.get_market_hours(markets, date=date)

    lines: list[str] = []
    for market_type, sessions in data.items():
        for market_name, info in sessions.items():
            product = info.get("product", market_name)
            is_open = info.get("isOpen", False)
            status = "OPEN" if is_open else "CLOSED"
            lines.append(f"**{product}** — {status}")

            for session_type in ("preMarket", "regularMarket", "postMarket"):
                session_hours = info.get("sessionHours", {}).get(session_type, [])
                for s in session_hours:
                    start = s.get("start", "")[:16]
                    end = s.get("end", "")[:16]
                    label = session_type.replace("Market", " Market").title()
                    lines.append(f"  {label}: {start} — {end}")

    return "\n".join(lines) if lines else "No market hours data available."


async def search_instruments(
    client: SchwabClient,
    symbol: str,
    projection: str = "symbol-search",
) -> str:
    """Search for instruments by symbol or name.

    Args:
        symbol: Search term — ticker, partial name, or CUSIP.
        projection: Search type: "symbol-search", "symbol-regex",
            "desc-search", "desc-regex", or "fundamental".
    """
    data = await client.search_instruments(symbol, projection=projection)

    instruments = data.get("instruments", [])
    if not instruments:
        return f"No instruments found for '{symbol}'."

    lines = [f"**Instrument Search: '{symbol}'** ({len(instruments)} results)\n"]

    for inst in instruments[:25]:
        sym = inst.get("symbol", "?")
        desc = inst.get("description", "")
        asset_type = inst.get("assetType", "")
        exchange = inst.get("exchange", "")
        cusip = inst.get("cusip", "")

        line = f"- **{sym}** ({asset_type}) — {desc}"
        if exchange:
            line += f" [{exchange}]"
        if cusip:
            line += f" CUSIP:{cusip}"

        # Include fundamental data if present
        fund = inst.get("fundamental", {})
        if fund:
            pe = fund.get("peRatio", 0)
            div_yield = fund.get("divYield", 0)
            mkt_cap = fund.get("marketCap", 0)
            extras = []
            if pe:
                extras.append(f"P/E:{pe:.1f}")
            if div_yield:
                extras.append(f"Yield:{div_yield:.2f}%")
            if mkt_cap:
                if mkt_cap >= 1e9:
                    extras.append(f"MktCap:${mkt_cap / 1e9:.1f}B")
                else:
                    extras.append(f"MktCap:${mkt_cap / 1e6:.0f}M")
            if extras:
                line += f" | {' | '.join(extras)}"

        lines.append(line)

    if len(instruments) > 25:
        lines.append(f"\n_Showing 25 of {len(instruments)} results._")

    return "\n".join(lines)
