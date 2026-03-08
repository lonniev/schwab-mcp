"""Tests for option chain tool with mocked responses."""

from datetime import date, timedelta
from unittest.mock import AsyncMock

from tools.options import get_option_chain


def _mock_client(response_data: dict) -> AsyncMock:
    client = AsyncMock()
    client.get_option_chain.return_value = response_data
    return client


def _mock_chain_data() -> dict:
    exp = (date.today() + timedelta(days=14)).isoformat()
    return {
        "underlyingPrice": 185.00,
        "callExpDateMap": {
            f"{exp}:14": {
                "190.0": [
                    {
                        "symbol": "AAPL  260227C00190000",
                        "strikePrice": 190.0,
                        "expirationDate": exp,
                        "daysToExpiration": 14,
                        "bid": 1.50,
                        "ask": 1.65,
                        "last": 1.55,
                        "totalVolume": 500,
                        "openInterest": 1200,
                        "volatility": 28.5,
                        "delta": 0.35,
                        "gamma": 0.04,
                        "theta": -0.08,
                    }
                ],
                "195.0": [
                    {
                        "symbol": "AAPL  260227C00195000",
                        "strikePrice": 195.0,
                        "expirationDate": exp,
                        "daysToExpiration": 14,
                        "bid": 0.50,
                        "ask": 0.60,
                        "last": 0.55,
                        "totalVolume": 200,
                        "openInterest": 800,
                        "volatility": 30.0,
                        "delta": 0.15,
                        "gamma": 0.02,
                        "theta": -0.05,
                    }
                ],
            }
        },
        "putExpDateMap": {
            f"{exp}:14": {
                "180.0": [
                    {
                        "symbol": "AAPL  260227P00180000",
                        "strikePrice": 180.0,
                        "expirationDate": exp,
                        "daysToExpiration": 14,
                        "bid": 1.80,
                        "ask": 1.95,
                        "last": 1.85,
                        "totalVolume": 350,
                        "openInterest": 950,
                        "volatility": 27.0,
                        "delta": -0.30,
                        "gamma": 0.03,
                        "theta": -0.07,
                    }
                ],
                "175.0": [
                    {
                        "symbol": "AAPL  260227P00175000",
                        "strikePrice": 175.0,
                        "expirationDate": exp,
                        "daysToExpiration": 14,
                        "bid": 0.40,
                        "ask": 0.50,
                        "last": 0.45,
                        "totalVolume": 100,
                        "openInterest": 10,  # Below min OI threshold
                        "volatility": 26.0,
                        "delta": -0.10,
                        "gamma": 0.01,
                        "theta": -0.03,
                    }
                ],
            }
        },
    }


async def test_option_chain_filters_by_oi():
    """Contracts with OI < 25 are excluded."""
    client = _mock_client(_mock_chain_data())
    result = await get_option_chain(client, "AAPL")

    assert "175.0" not in result  # OI = 10, should be filtered out
    assert "190.0" in result or "190.00" in result
    assert "180.0" in result or "180.00" in result


async def test_option_chain_shows_greeks():
    """Greeks columns are present in output."""
    client = _mock_client(_mock_chain_data())
    result = await get_option_chain(client, "AAPL")

    assert "Delta" in result
    assert "Theta" in result
    assert "0.35" in result or "0.350" in result  # delta of 190 call


async def test_option_chain_shows_otm_pct():
    """OTM percentage is calculated and displayed."""
    client = _mock_client(_mock_chain_data())
    result = await get_option_chain(client, "AAPL")

    assert "OTM" in result


async def test_option_chain_empty():
    """Returns friendly message when no contracts match filters."""
    data = {"underlyingPrice": 100.0, "callExpDateMap": {}, "putExpDateMap": {}}
    client = _mock_client(data)
    result = await get_option_chain(client, "XYZ")
    assert "No option contracts" in result


async def test_option_chain_underlying_price_in_header():
    """Underlying price is shown in the output header."""
    client = _mock_client(_mock_chain_data())
    result = await get_option_chain(client, "AAPL")
    assert "185.00" in result
