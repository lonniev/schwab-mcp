"""Tests for market data tools with mocked responses."""

from unittest.mock import AsyncMock, MagicMock

from tools.market import get_price_history, get_quote


def _mock_client(response_data: dict) -> AsyncMock:
    mock_response = MagicMock()
    mock_response.json.return_value = response_data
    mock_response.raise_for_status.return_value = None

    client = AsyncMock()
    client.get_quotes.return_value = mock_response
    client.get_price_history.return_value = mock_response
    return client


async def test_get_quote_single():
    """Single symbol quote is formatted correctly."""
    data = {
        "AAPL": {
            "quote": {
                "lastPrice": 185.50,
                "bidPrice": 185.45,
                "askPrice": 185.55,
                "totalVolume": 45000000,
                "netPercentChange": 1.25,
                "52WeekHigh": 199.62,
                "52WeekLow": 155.00,
            },
            "reference": {},
        }
    }
    client = _mock_client(data)
    result = await get_quote(client, "AAPL")

    assert "AAPL" in result
    assert "185.50" in result
    assert "45,000,000" in result


async def test_get_quote_multiple():
    """Multiple symbols are all included."""
    aapl_quote = {
        "lastPrice": 185.50, "bidPrice": 0, "askPrice": 0,
        "totalVolume": 0, "netPercentChange": 0,
        "52WeekHigh": 0, "52WeekLow": 0,
    }
    msft_quote = {
        "lastPrice": 420.00, "bidPrice": 0, "askPrice": 0,
        "totalVolume": 0, "netPercentChange": 0,
        "52WeekHigh": 0, "52WeekLow": 0,
    }
    data = {
        "AAPL": {"quote": aapl_quote, "reference": {}},
        "MSFT": {"quote": msft_quote, "reference": {}},
    }
    client = _mock_client(data)
    result = await get_quote(client, "AAPL, MSFT")

    assert "AAPL" in result
    assert "MSFT" in result


async def test_get_price_history():
    """Price history returns formatted candle table."""
    data = {
        "candles": [
            {
                "datetime": 1707868800000, "open": 180.0,
                "high": 185.0, "low": 179.0, "close": 184.0,
                "volume": 50000000,
            },
            {
                "datetime": 1707955200000, "open": 184.0,
                "high": 186.0, "low": 183.0, "close": 185.5,
                "volume": 48000000,
            },
        ]
    }
    client = _mock_client(data)
    result = await get_price_history(client, "AAPL")

    assert "AAPL" in result
    assert "180.00" in result
    assert "2 candles" in result


async def test_get_price_history_empty():
    """Empty candle data returns friendly message."""
    client = _mock_client({"candles": []})
    result = await get_price_history(client, "XYZ")
    assert "No price history" in result
