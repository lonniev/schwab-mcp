"""Tests for account tools with mocked Schwab API responses."""

from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock

from tools.account import get_account_balances, get_positions


def _mock_positions_response():
    """Mock Schwab account response with options positions forming a spread."""
    exp = (date.today() + timedelta(days=14)).isoformat()
    return {
        "securitiesAccount": {
            "positions": [
                {
                    "instrument": {
                        "assetType": "OPTION",
                        "symbol": "AAPL  260227P00200000",
                        "underlyingSymbol": "AAPL",
                        "putCall": "PUT",
                        "strikePrice": 200.0,
                        "expirationDate": exp,
                    },
                    "shortQuantity": 1,
                    "longQuantity": 0,
                    "averagePrice": 2.50,
                    "marketValue": -180.0,
                    "shortOpenProfitLoss": 70.0,
                    "longOpenProfitLoss": 0.0,
                },
                {
                    "instrument": {
                        "assetType": "OPTION",
                        "symbol": "AAPL  260227P00197500",
                        "underlyingSymbol": "AAPL",
                        "putCall": "PUT",
                        "strikePrice": 197.50,
                        "expirationDate": exp,
                    },
                    "shortQuantity": 0,
                    "longQuantity": 1,
                    "averagePrice": 1.20,
                    "marketValue": 90.0,
                    "shortOpenProfitLoss": 0.0,
                    "longOpenProfitLoss": -30.0,
                },
                {
                    "instrument": {
                        "assetType": "EQUITY",
                        "symbol": "SPY",
                    },
                    "longQuantity": 10,
                    "shortQuantity": 0,
                    "averagePrice": 450.0,
                    "marketValue": 4800.0,
                    "longOpenProfitLoss": 300.0,
                    "shortOpenProfitLoss": 0.0,
                },
            ]
        }
    }


def _mock_client(response_data: dict) -> AsyncMock:
    mock_response = MagicMock()
    mock_response.json.return_value = response_data
    mock_response.raise_for_status.return_value = None

    client = AsyncMock()
    client.get_account.return_value = mock_response
    return client


async def test_get_positions_with_spread():
    """Positions are parsed and spreads are detected."""
    client = _mock_client(_mock_positions_response())
    result = await get_positions(client, "FAKE_HASH")

    assert "Bull Put Spread" in result
    assert "AAPL" in result
    assert "200.0" in result or "200.00" in result
    assert "197.5" in result or "197.50" in result
    assert "SPY" in result


async def test_get_positions_empty():
    """Returns friendly message when no positions exist."""
    client = _mock_client({"securitiesAccount": {"positions": []}})
    result = await get_positions(client, "FAKE_HASH")
    assert "No open positions" in result


async def test_get_positions_no_positions_key():
    """Handles missing positions key gracefully."""
    client = _mock_client({"securitiesAccount": {}})
    result = await get_positions(client, "FAKE_HASH")
    assert "No open positions" in result


async def test_get_account_balances():
    """Balances are parsed into readable format."""
    data = {
        "securitiesAccount": {
            "currentBalances": {
                "cashBalance": 10000.0,
                "buyingPower": 20000.0,
                "liquidationValue": 50000.0,
                "dayTradingBuyingPower": 150.0,
            }
        }
    }
    client = _mock_client(data)
    result = await get_account_balances(client, "FAKE_HASH")

    assert "10,000.00" in result
    assert "20,000.00" in result
    assert "50,000.00" in result
