"""Options tools — option chain retrieval and filtering."""

from datetime import date, timedelta

from models import OptionContract
from schwab_client import SchwabClient


async def get_option_chain(
    client: SchwabClient,
    symbol: str,
    strike_count: int = 20,
    contract_type: str = "ALL",
    days_to_expiration: int = 21,
) -> str:
    """Get filtered option chain data for spread evaluation.

    Returns option contracts filtered by DTE and open interest,
    with Greeks and OTM percentage for efficient spread scanning.

    Args:
        symbol: Underlying ticker symbol.
        strike_count: Number of strikes around ATM to include.
        contract_type: "ALL", "CALL", or "PUT".
        days_to_expiration: Maximum days to expiration to include.
    """
    from_date = date.today()
    to_date = from_date + timedelta(days=days_to_expiration)

    data = await client.get_option_chain(
        symbol.upper(),
        contractType=contract_type.upper(),
        strikeCount=strike_count,
        includeUnderlyingQuote=True,
        strategy="SINGLE",
        fromDate=from_date.isoformat(),
        toDate=to_date.isoformat(),
    )

    underlying_price = data.get("underlyingPrice", 0.0)
    if not underlying_price:
        underlying = data.get("underlying", {})
        underlying_price = underlying.get("last", underlying.get("mark", 0.0))

    min_oi = 25
    contracts: list[OptionContract] = []

    for map_key in ("callExpDateMap", "putExpDateMap"):
        exp_map = data.get(map_key, {})
        put_call = "CALL" if "call" in map_key.lower() else "PUT"

        for exp_key, strikes in exp_map.items():
            for strike_key, contract_list in strikes.items():
                for c in contract_list:
                    oi = c.get("openInterest", 0)
                    if oi < min_oi:
                        continue

                    strike = c.get("strikePrice", 0.0)
                    if underlying_price > 0:
                        if put_call == "PUT":
                            otm_pct = (underlying_price - strike) / underlying_price * 100
                        else:
                            otm_pct = (strike - underlying_price) / underlying_price * 100
                    else:
                        otm_pct = 0.0

                    exp_str = c.get("expirationDate", "")[:10]
                    try:
                        exp_date = date.fromisoformat(exp_str)
                    except (ValueError, TypeError):
                        exp_date = date.today()

                    contracts.append(
                        OptionContract(
                            symbol=c.get("symbol", ""),
                            strike=strike,
                            expiration=exp_date,
                            dte=c.get("daysToExpiration", 0),
                            put_call=put_call,
                            bid=c.get("bid", 0.0),
                            ask=c.get("ask", 0.0),
                            last=c.get("last", 0.0),
                            volume=c.get("totalVolume", 0),
                            open_interest=oi,
                            implied_volatility=c.get("volatility", 0.0),
                            delta=c.get("delta", 0.0),
                            gamma=c.get("gamma", 0.0),
                            theta=c.get("theta", 0.0),
                            otm_pct=round(otm_pct, 2),
                        )
                    )

    if not contracts:
        return (
            f"No option contracts found for {symbol.upper()} "
            f"within {days_to_expiration} DTE with OI >= {min_oi}."
        )

    contracts.sort(key=lambda c: (c.expiration, c.put_call, c.strike))

    lines = [
        f"**{symbol.upper()} Option Chain** | Underlying: ${underlying_price:.2f} | "
        f"Showing {len(contracts)} contracts (OI >= {min_oi}, DTE <= {days_to_expiration})\n"
    ]
    lines.append(
        "| Exp | DTE | P/C | Strike | OTM% | Bid | Ask | Last | Vol | OI | IV | Delta | Theta |"
    )
    lines.append(
        "|-----|-----|-----|--------|------|-----|-----|------|-----|----|----|-------|-------|"
    )

    for c in contracts:
        atm_flag = " *" if abs(c.otm_pct) < 1.0 else ""
        lines.append(
            f"| {c.expiration} | {c.dte} | {c.put_call} | ${c.strike:.2f}{atm_flag} | "
            f"{c.otm_pct:+.1f}% | ${c.bid:.2f} | ${c.ask:.2f} | ${c.last:.2f} | "
            f"{c.volume:,} | {c.open_interest:,} | {c.implied_volatility:.1f}% | "
            f"{c.delta:.3f} | {c.theta:.3f} |"
        )

    return "\n".join(lines)
