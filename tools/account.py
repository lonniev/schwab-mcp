"""Account tools — positions, balances, orders, and transactions."""

from datetime import date, datetime, timedelta, timezone

from models import (
    AccountBalances,
    EquityPosition,
    OptionPosition,
    SpreadPosition,
)
from schwab_client import SchwabClient


def _parse_occ_symbol(occ: str) -> dict:
    """Parse an OCC option symbol like 'GLD   260318P00480000'.

    Format: SYMBOL (padded to 6) + YYMMDD + C/P + strike*1000 (8 digits).
    The symbol portion may be shorter than 6 chars with trailing spaces,
    or Schwab may use a compact format like 'GLD_031826P480'.
    """
    import re

    # Try compact Schwab format: UNDERLYING_MMDDYYC{strike}
    compact = re.match(
        r"^([A-Z]+)_(\d{2})(\d{2})(\d{2})([CP])([\d.]+)$", occ,
    )
    if compact:
        sym, mm, dd, yy, pc, strike = compact.groups()
        return {
            "underlying": sym,
            "expiration": f"20{yy}-{mm}-{dd}",
            "put_call": "PUT" if pc == "P" else "CALL",
            "strike": float(strike),
        }

    # Try standard OCC format: 6-char padded symbol + YYMMDD + C/P + 8-digit strike
    occ_match = re.match(
        r"^(.{6})(\d{2})(\d{2})(\d{2})([CP])(\d{8})$", occ,
    )
    if occ_match:
        sym, yy, mm, dd, pc, strike_raw = occ_match.groups()
        return {
            "underlying": sym.strip(),
            "expiration": f"20{yy}-{mm}-{dd}",
            "put_call": "PUT" if pc == "P" else "CALL",
            "strike": int(strike_raw) / 1000.0,
        }

    return {}


def _parse_option_symbol(instrument: dict) -> dict:
    """Extract option details from a Schwab instrument dict.

    Tries explicit fields first (strikePrice, expirationDate), then
    falls back to parsing the OCC symbol which always encodes them.
    """
    symbol = instrument.get("symbol", "")
    underlying = instrument.get("underlyingSymbol", "")
    put_call = instrument.get("putCall", "UNKNOWN")
    strike = instrument.get("strikePrice", 0.0)
    expiration = instrument.get("expirationDate", "")

    # Fall back to OCC symbol parsing if explicit fields are missing
    if not strike or not expiration:
        parsed = _parse_occ_symbol(symbol)
        if parsed:
            if not strike:
                strike = parsed.get("strike", 0.0)
            if not expiration:
                expiration = parsed.get("expiration", "")
            if not underlying:
                underlying = parsed.get("underlying", "")
            if put_call == "UNKNOWN":
                put_call = parsed.get("put_call", "UNKNOWN")

    # Also try parsing the description as last resort: "GLD 03/18/2026 480.0 P"
    if (not strike or not expiration) and instrument.get("description"):
        import re

        desc = instrument["description"]
        desc_match = re.match(
            r"^([A-Z]+)\s+(\d{2}/\d{2}/\d{4})\s+([\d.]+)\s+([CP])$", desc,
        )
        if desc_match:
            sym, date_str, strike_str, pc = desc_match.groups()
            if not underlying:
                underlying = sym
            if not expiration:
                mm, dd, yyyy = date_str.split("/")
                expiration = f"{yyyy}-{mm}-{dd}"
            if not strike:
                strike = float(strike_str)
            if put_call == "UNKNOWN":
                put_call = "PUT" if pc == "P" else "CALL"

    return {
        "symbol": symbol,
        "underlying": underlying,
        "put_call": put_call,
        "strike": strike,
        "expiration": expiration,
    }


def _compute_dte(expiration_str: str) -> int:
    """Compute days to expiration from an ISO date string."""
    try:
        exp = date.fromisoformat(expiration_str[:10])
        return max((exp - date.today()).days, 0)
    except (ValueError, TypeError):
        return 0


def _extract_last_price(quote: dict) -> float | None:
    """Pull the reliable last equity price from a Schwab quote entry.

    Mirrors the extraction in tools/market.py. Returns None when the quote
    is missing or malformed, so callers can degrade gracefully.
    """
    if not isinstance(quote, dict):
        return None
    quote_data = quote.get("quote", {})
    regular = quote.get("regular", {})
    last = quote_data.get("lastPrice", regular.get("lastPrice"))
    return last if isinstance(last, (int, float)) and last else None


def _moneyness(put_call: str, underlying_price: float, short_strike: float) -> str:
    """Classify the SHORT leg as ITM / OTM / ATM against the live underlying."""
    if underlying_price == short_strike:
        return "ATM"
    if put_call == "PUT":
        return "ITM" if underlying_price < short_strike else "OTM"
    return "ITM" if underlying_price > short_strike else "OTM"


def _detect_spreads(
    options: list[OptionPosition],
    underlying_prices: dict[str, float | None] | None = None,
) -> tuple[list[SpreadPosition], list[OptionPosition]]:
    """Group option positions into spreads where possible.

    A spread is two options on the same underlying with the same expiration
    but different strikes, where one is short and one is long.

    ``underlying_prices`` maps an underlying symbol to its live equity price
    (from get_quotes). When a price is present, each spread is enriched with
    the short-strike distance and moneyness — the authoritative decision
    inputs — since Schwab's option combo mark is unreliable for deep-ITM legs.
    """
    underlying_prices = underlying_prices or {}
    spreads: list[SpreadPosition] = []
    used: set[int] = set()

    for i, a in enumerate(options):
        if i in used:
            continue
        for j, b in enumerate(options):
            if j in used or j <= i:
                continue
            if (
                a.underlying == b.underlying
                and a.expiration == b.expiration
                and a.put_call == b.put_call
                and a.strike != b.strike
                and (a.quantity < 0) != (b.quantity < 0)
            ):
                short_leg = a if a.quantity < 0 else b
                long_leg = b if a.quantity < 0 else a

                if short_leg.put_call == "PUT":
                    spread_type = "Bull Put Spread"
                else:
                    spread_type = "Bear Call Spread"

                credit = abs(short_leg.avg_price) - abs(long_leg.avg_price)
                width = abs(short_leg.strike - long_leg.strike)
                max_loss = width - credit
                current_value = abs(short_leg.market_value) - abs(long_leg.market_value)

                underlying_price = underlying_prices.get(a.underlying)
                distance: float | None = None
                distance_pct: float | None = None
                moneyness: str | None = None
                if underlying_price:
                    distance = round(underlying_price - short_leg.strike, 2)
                    distance_pct = round(distance / underlying_price * 100, 2)
                    moneyness = _moneyness(
                        short_leg.put_call, underlying_price, short_leg.strike
                    )

                spreads.append(
                    SpreadPosition(
                        underlying=a.underlying,
                        spread_type=spread_type,
                        short_leg=short_leg,
                        long_leg=long_leg,
                        credit_received=round(credit, 2),
                        max_loss=round(max_loss, 2),
                        current_value=round(current_value, 2),
                        unrealized_pl=round(
                            short_leg.unrealized_pl + long_leg.unrealized_pl, 2
                        ),
                        underlying_price=(
                            round(underlying_price, 2) if underlying_price else None
                        ),
                        short_strike_distance=distance,
                        short_strike_distance_pct=distance_pct,
                        moneyness=moneyness,
                    )
                )
                used.add(i)
                used.add(j)
                break

    remaining = [opt for i, opt in enumerate(options) if i not in used]
    return spreads, remaining


async def _fetch_underlying_prices(
    client: SchwabClient, options: list[OptionPosition]
) -> dict[str, float | None]:
    """Fetch live equity prices for the options' underlyings, best-effort.

    Returns a symbol->price map. Any failure (auth, network, malformed
    payload) degrades to an empty map so positions output never breaks — the
    spread rows simply fall back to "Underlying: n/a".
    """
    symbols = sorted({o.underlying for o in options if o.underlying})
    if not symbols:
        return {}
    try:
        quotes = await client.get_quotes(symbols)
    except Exception:
        return {}
    if not isinstance(quotes, dict):
        return {}
    return {sym: _extract_last_price(quotes.get(sym, {})) for sym in symbols}


async def get_positions(client: SchwabClient, account_hash: str) -> str:
    """Get current positions with options spread detection.

    Returns structured position data including DTE, P&L,
    and automatic spread pairing for options positions.
    """
    data = await client.get_account(account_hash, fields="positions")

    positions = (
        data.get("securitiesAccount", {}).get("positions", [])
    )

    if not positions:
        return "No open positions."

    options: list[OptionPosition] = []
    equities: list[EquityPosition] = []

    for pos in positions:
        instrument = pos.get("instrument", {})
        asset_type = instrument.get("assetType", "")

        if asset_type == "OPTION":
            details = _parse_option_symbol(instrument)
            exp_str = details["expiration"]
            exp_date = date.fromisoformat(exp_str[:10]) if exp_str else date.today()

            options.append(
                OptionPosition(
                    symbol=details["symbol"],
                    underlying=details["underlying"],
                    put_call=details["put_call"],
                    strike=details["strike"],
                    expiration=exp_date,
                    dte=_compute_dte(exp_str),
                    quantity=int(pos.get("longQuantity", 0) - pos.get("shortQuantity", 0)),
                    avg_price=pos.get("averagePrice", 0.0),
                    market_value=pos.get("marketValue", 0.0),
                    unrealized_pl=pos.get("longOpenProfitLoss", 0.0)
                    + pos.get("shortOpenProfitLoss", 0.0),
                )
            )
        elif asset_type == "EQUITY":
            equities.append(
                EquityPosition(
                    symbol=instrument.get("symbol", ""),
                    quantity=pos.get("longQuantity", 0) - pos.get("shortQuantity", 0),
                    avg_cost=pos.get("averagePrice", 0.0),
                    current_price=pos.get("marketValue", 0.0)
                    / max(
                        pos.get("longQuantity", 0) - pos.get("shortQuantity", 0), 1
                    ),
                    market_value=pos.get("marketValue", 0.0),
                    unrealized_pl=pos.get("longOpenProfitLoss", 0.0)
                    + pos.get("shortOpenProfitLoss", 0.0),
                )
            )

    underlying_prices = await _fetch_underlying_prices(client, options)
    spreads, remaining_options = _detect_spreads(options, underlying_prices)

    lines: list[str] = []

    if spreads:
        lines.append("## Spreads")
        for s in spreads:
            if s.underlying_price is not None:
                underlying_col = (
                    f"Underlying: ${s.underlying_price:.2f} | "
                    f"ShortDist: ${s.short_strike_distance:+.2f} "
                    f"({s.short_strike_distance_pct:+.1f}%) {s.moneyness} | "
                )
            else:
                underlying_col = "Underlying: n/a | "
            lines.append(
                f"- **{s.underlying} {s.spread_type}** "
                f"({s.short_leg.strike}/{s.long_leg.strike} "
                f"{s.short_leg.put_call} exp {s.short_leg.expiration}, "
                f"DTE {s.short_leg.dte}) | "
                f"{underlying_col}"
                f"Credit: ${s.credit_received:.2f} | "
                f"Max Loss: ${s.max_loss:.2f} | "
                f"EstClose (mark×100): ${s.current_value:.2f} | "
                f"P&L: ${s.unrealized_pl:.2f}"
            )

    if remaining_options:
        lines.append("## Options (unmatched)")
        for o in remaining_options:
            lines.append(
                f"- {o.underlying} {o.strike} {o.put_call} "
                f"exp {o.expiration} (DTE {o.dte}) | "
                f"Qty: {o.quantity} | "
                f"Avg: ${o.avg_price:.2f} | "
                f"MktVal: ${o.market_value:.2f} | "
                f"P&L: ${o.unrealized_pl:.2f}"
            )

    if equities:
        lines.append("## Equities")
        for e in equities:
            lines.append(
                f"- {e.symbol} | Qty: {e.quantity:.0f} | "
                f"Avg: ${e.avg_cost:.2f} | "
                f"Price: ${e.current_price:.2f} | "
                f"P&L: ${e.unrealized_pl:.2f}"
            )

    return "\n".join(lines)


async def get_account_balances(client: SchwabClient, account_hash: str) -> str:
    """Get account summary: cash, buying power, net liquidation, day P&L.

    Day P&L is computed from Schwab's initialBalances vs currentBalances
    snapshots (currentBalances.liquidationValue − initialBalances.liquidationValue).
    Schwab's API does not expose a single "dayProfitLoss" field on the
    account; the delta against the start-of-day snapshot is the canonical
    session-P&L measure. When either snapshot is missing we report 0.0
    rather than a misleading large number derived from a zero baseline.
    """
    data = await client.get_account(account_hash)

    securities = data.get("securitiesAccount", {})
    current = securities.get("currentBalances", {})
    initial = securities.get("initialBalances", {})

    current_liq = current.get("liquidationValue", 0.0)
    initial_liq = initial.get("liquidationValue", 0.0)
    # Only compute the delta when both snapshots are present (non-zero).
    # If one is missing, treating zero as the baseline would print today's
    # full equity as "Day P&L", which is the bug we are fixing.
    day_pl = current_liq - initial_liq if current_liq and initial_liq else 0.0

    # Schwab sometimes returns initialBalances.liquidationValue that is
    # present-but-stale or partial — large enough to evade the "missing
    # snapshot" check above but so far off the current equity that the
    # computed Day P&L is nonsensical (e.g. $17,442 P&L on an $8,847
    # account). When the absolute Day P&L exceeds half of current
    # liquidation value, treat the snapshot as suspect and report 0.0
    # rather than a misleading number. A legitimate 50%-in-a-session
    # move is implausible for any normal account; we'd rather underreport
    # in that rare case than report nonsense in the common one.
    if current_liq and abs(day_pl) > current_liq * 0.5:
        day_pl = 0.0

    acct = AccountBalances(
        cash_balance=current.get("cashBalance", 0.0),
        buying_power=current.get("buyingPower", 0.0),
        net_liquidation=current_liq,
        day_pl=day_pl,
    )

    return (
        f"**Cash Balance:** ${acct.cash_balance:,.2f}\n"
        f"**Buying Power:** ${acct.buying_power:,.2f}\n"
        f"**Net Liquidation:** ${acct.net_liquidation:,.2f}\n"
        f"**Day P&L:** ${acct.day_pl:,.2f}"
    )


# ---------------------------------------------------------------------------
# Orders
# ---------------------------------------------------------------------------


def _default_date_range(days_back: int = 30) -> tuple[str, str]:
    """Return (from_date, to_date) ISO strings defaulting to last N days."""
    now = datetime.now(timezone.utc)
    return (now - timedelta(days=days_back)).strftime("%Y-%m-%dT00:00:00.000Z"), now.strftime(
        "%Y-%m-%dT%H:%M:%S.000Z"
    )


def _format_order_leg(leg: dict) -> str:
    """Format a single order leg for display."""
    inst = leg.get("instrument", {})
    symbol = inst.get("symbol", "?")
    action = leg.get("instruction", "?")
    qty = leg.get("quantity", 0)
    return f"{action} {qty}x {symbol}"


def _format_order(order: dict) -> str:
    """Format a single order into a readable markdown line."""
    order_id = order.get("orderId", "?")
    status = order.get("status", "?")
    order_type = order.get("orderType", "?")
    entered = order.get("enteredTime", "")[:19]
    price = order.get("price", order.get("stopPrice", 0))

    legs = order.get("orderLegCollection", [])
    leg_str = " / ".join(_format_order_leg(leg) for leg in legs)

    filled_qty = order.get("filledQuantity", 0)
    fill_price = order.get("orderActivityCollection", [{}])
    avg_fill = ""
    if fill_price:
        execs = []
        for activity in order.get("orderActivityCollection", []):
            for exec_leg in activity.get("executionLegs", []):
                execs.append(exec_leg.get("price", 0))
        if execs:
            avg_fill = f" @ ${sum(execs) / len(execs):.2f}"

    return (
        f"- **{order_id}** [{status}] {order_type} | {leg_str} | "
        f"Price: ${price:.2f}{avg_fill} | Filled: {filled_qty} | {entered}"
    )


async def get_orders(
    client: SchwabClient,
    account_hash: str,
    from_date: str | None = None,
    to_date: str | None = None,
    status_filter: str | None = None,
) -> str:
    """Get order history. Defaults to last 30 days."""
    if not from_date or not to_date:
        from_date, to_date = _default_date_range(30)

    orders = await client.get_orders(
        account_hash, from_date, to_date, status=status_filter
    )

    if not orders:
        return "No orders found in the specified date range."

    lines = [f"## Orders ({len(orders)} found)"]
    for order in orders:
        lines.append(_format_order(order))

    return "\n".join(lines)


async def get_order(
    client: SchwabClient,
    account_hash: str,
    order_id: str,
) -> str:
    """Get a single order by ID."""
    order = await client.get_order(account_hash, order_id)
    return _format_order(order)


# ---------------------------------------------------------------------------
# Transactions
# ---------------------------------------------------------------------------


def _format_transaction(txn: dict) -> str:
    """Format a single transaction into a readable markdown line."""
    txn_id = txn.get("activityId", txn.get("transactionId", "?"))
    txn_type = txn.get("type", "?")
    txn_date = txn.get("tradeDate", txn.get("transactionDate", ""))[:10]
    description = txn.get("description", "")

    net_amount = txn.get("netAmount", 0)

    # Extract instrument info from transferItems
    symbols = []
    for item in txn.get("transferItems", []):
        inst = item.get("instrument", {})
        sym = inst.get("symbol", "")
        if sym:
            qty = item.get("amount", 0)
            symbols.append(f"{qty}x {sym}" if qty else sym)

    sym_str = " | ".join(symbols) if symbols else description

    return (
        f"- **{txn_id}** [{txn_type}] {txn_date} | {sym_str} | "
        f"Net: ${net_amount:,.2f}"
    )


async def get_transactions(
    client: SchwabClient,
    account_hash: str,
    from_date: str | None = None,
    to_date: str | None = None,
    transaction_types: str | None = None,
) -> str:
    """Get transaction history. Defaults to last 30 days."""
    if not from_date or not to_date:
        from_date, to_date = _default_date_range(30)

    txns = await client.get_transactions(
        account_hash, from_date, to_date, transaction_types=transaction_types
    )

    if not txns:
        return "No transactions found in the specified date range."

    lines = [f"## Transactions ({len(txns)} found)"]
    for txn in txns:
        lines.append(_format_transaction(txn))

    return "\n".join(lines)


async def get_transaction(
    client: SchwabClient,
    account_hash: str,
    transaction_id: str,
) -> str:
    """Get a single transaction by ID."""
    txn = await client.get_transaction(account_hash, transaction_id)
    return _format_transaction(txn)
