"""Tests for account tools with mocked Schwab API responses."""

from datetime import date, timedelta
from unittest.mock import AsyncMock

from tools.account import (
    _parse_occ_symbol,
    _parse_option_symbol,
    get_account_balances,
    get_order,
    get_orders,
    get_positions,
    get_transaction,
    get_transactions,
)


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
    client = AsyncMock()
    client.get_account.return_value = response_data
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


# ---------------------------------------------------------------------------
# OCC symbol parsing tests
# ---------------------------------------------------------------------------


class TestParseOccSymbol:
    """Tests for _parse_occ_symbol."""

    def test_standard_occ_format(self):
        """Parses standard 6+6+1+8 OCC format."""
        result = _parse_occ_symbol("GLD   260318P00480000")
        assert result["underlying"] == "GLD"
        assert result["expiration"] == "2026-03-18"
        assert result["put_call"] == "PUT"
        assert result["strike"] == 480.0

    def test_standard_occ_call(self):
        """Parses a call option in standard OCC format."""
        result = _parse_occ_symbol("AAPL  260227C00200000")
        assert result["underlying"] == "AAPL"
        assert result["expiration"] == "2026-02-27"
        assert result["put_call"] == "CALL"
        assert result["strike"] == 200.0

    def test_standard_occ_fractional_strike(self):
        """Parses fractional strikes (e.g., 197.50)."""
        result = _parse_occ_symbol("AAPL  260227P00197500")
        assert result["strike"] == 197.5

    def test_compact_schwab_format(self):
        """Parses Schwab compact format: SYM_MMDDYYC{strike}."""
        result = _parse_occ_symbol("GLD_031826P480")
        assert result["underlying"] == "GLD"
        assert result["expiration"] == "2026-03-18"
        assert result["put_call"] == "PUT"
        assert result["strike"] == 480.0

    def test_compact_schwab_decimal_strike(self):
        """Parses compact format with decimal strike."""
        result = _parse_occ_symbol("CAT_031326P737.5")
        assert result["underlying"] == "CAT"
        assert result["strike"] == 737.5

    def test_unrecognized_returns_empty(self):
        """Returns empty dict for unrecognized formats."""
        assert _parse_occ_symbol("GARBAGE") == {}


class TestParseOptionSymbolFallback:
    """Tests for _parse_option_symbol falling back to OCC parsing."""

    def test_uses_explicit_fields_when_present(self):
        """Prefers explicit strikePrice and expirationDate."""
        instrument = {
            "symbol": "GLD   260318P00480000",
            "underlyingSymbol": "GLD",
            "putCall": "PUT",
            "strikePrice": 480.0,
            "expirationDate": "2026-03-18",
        }
        result = _parse_option_symbol(instrument)
        assert result["strike"] == 480.0
        assert result["expiration"] == "2026-03-18"

    def test_falls_back_to_occ_when_fields_missing(self):
        """Parses OCC symbol when strikePrice and expirationDate are absent."""
        instrument = {
            "symbol": "GLD   260318P00480000",
            "underlyingSymbol": "GLD",
            "putCall": "PUT",
        }
        result = _parse_option_symbol(instrument)
        assert result["strike"] == 480.0
        assert result["expiration"] == "2026-03-18"
        assert result["put_call"] == "PUT"

    def test_falls_back_to_description(self):
        """Parses description as last resort."""
        instrument = {
            "symbol": "UNKNOWN",
            "description": "ABBV 03/20/2026 222.5 P",
        }
        result = _parse_option_symbol(instrument)
        assert result["strike"] == 222.5
        assert result["expiration"] == "2026-03-20"
        assert result["put_call"] == "PUT"
        assert result["underlying"] == "ABBV"


async def test_get_positions_without_explicit_option_fields():
    """Positions parse correctly when Schwab omits strikePrice/expirationDate."""
    exp_occ = (date.today() + timedelta(days=7)).strftime("%y%m%d")
    exp_iso = (date.today() + timedelta(days=7)).isoformat()
    data = {
        "securitiesAccount": {
            "positions": [
                {
                    "instrument": {
                        "assetType": "OPTION",
                        "symbol": f"GLD   {exp_occ}P00480000",
                        "underlyingSymbol": "GLD",
                        "putCall": "PUT",
                        # No strikePrice or expirationDate
                    },
                    "shortQuantity": 1,
                    "longQuantity": 0,
                    "averagePrice": 5.0,
                    "marketValue": -300.0,
                    "shortOpenProfitLoss": 200.0,
                    "longOpenProfitLoss": 0.0,
                },
                {
                    "instrument": {
                        "assetType": "OPTION",
                        "symbol": f"GLD   {exp_occ}P00478000",
                        "underlyingSymbol": "GLD",
                        "putCall": "PUT",
                        # No strikePrice or expirationDate
                    },
                    "shortQuantity": 0,
                    "longQuantity": 1,
                    "averagePrice": 3.0,
                    "marketValue": 200.0,
                    "shortOpenProfitLoss": 0.0,
                    "longOpenProfitLoss": -100.0,
                },
            ]
        }
    }
    client = _mock_client(data)
    result = await get_positions(client, "FAKE_HASH")

    assert "Bull Put Spread" in result
    assert "480.0" in result
    assert "478.0" in result
    assert "DTE 7" in result


# ---------------------------------------------------------------------------
# Order history tests
# ---------------------------------------------------------------------------


def _mock_orders_response():
    """Mock Schwab orders list response with a multi-leg spread order."""
    return [
        {
            "orderId": 12345,
            "status": "FILLED",
            "orderType": "NET_CREDIT",
            "enteredTime": "2026-03-01T10:30:00+0000",
            "price": 1.30,
            "filledQuantity": 1,
            "orderLegCollection": [
                {
                    "instruction": "SELL_TO_OPEN",
                    "quantity": 1,
                    "instrument": {"symbol": "GLD_031826P480", "assetType": "OPTION"},
                },
                {
                    "instruction": "BUY_TO_OPEN",
                    "quantity": 1,
                    "instrument": {"symbol": "GLD_031826P478", "assetType": "OPTION"},
                },
            ],
            "orderActivityCollection": [
                {
                    "executionLegs": [
                        {"price": 1.32},
                    ]
                }
            ],
        },
        {
            "orderId": 12346,
            "status": "CANCELED",
            "orderType": "LIMIT",
            "enteredTime": "2026-03-02T14:00:00+0000",
            "price": 150.00,
            "filledQuantity": 0,
            "orderLegCollection": [
                {
                    "instruction": "BUY",
                    "quantity": 10,
                    "instrument": {"symbol": "SPY", "assetType": "EQUITY"},
                },
            ],
            "orderActivityCollection": [],
        },
    ]


def _mock_orders_client(orders: list) -> AsyncMock:
    client = AsyncMock()
    client.get_orders.return_value = orders
    client.get_order.return_value = orders[0] if orders else {}
    return client


async def test_get_orders_with_spread():
    """Orders are parsed including multi-leg spreads."""
    client = _mock_orders_client(_mock_orders_response())
    result = await get_orders(client, "FAKE_HASH")

    assert "12345" in result
    assert "FILLED" in result
    assert "SELL_TO_OPEN" in result
    assert "BUY_TO_OPEN" in result
    assert "GLD_031826P480" in result
    assert "12346" in result
    assert "CANCELED" in result
    assert "2 found" in result


async def test_get_orders_empty():
    """Returns friendly message when no orders exist."""
    client = AsyncMock()
    client.get_orders.return_value = []
    result = await get_orders(client, "FAKE_HASH")
    assert "No orders found" in result


async def test_get_order_single():
    """Single order lookup returns formatted order."""
    client = _mock_orders_client(_mock_orders_response())
    result = await get_order(client, "FAKE_HASH", "12345")
    assert "12345" in result
    assert "FILLED" in result


# ---------------------------------------------------------------------------
# Transaction history tests
# ---------------------------------------------------------------------------


def _mock_transactions_response():
    """Mock Schwab transactions list."""
    return [
        {
            "activityId": 99001,
            "type": "TRADE",
            "tradeDate": "2026-03-01T00:00:00+0000",
            "description": "Sold 1 GLD Put",
            "netAmount": 130.00,
            "transferItems": [
                {
                    "instrument": {"symbol": "GLD_031826P480", "assetType": "OPTION"},
                    "amount": 1,
                },
            ],
        },
        {
            "activityId": 99002,
            "type": "DIVIDEND",
            "tradeDate": "2026-03-05T00:00:00+0000",
            "description": "CASH DIV ON 10 SHS",
            "netAmount": 4.50,
            "transferItems": [],
        },
    ]


def _mock_transactions_client(txns: list) -> AsyncMock:
    client = AsyncMock()
    client.get_transactions.return_value = txns
    client.get_transaction.return_value = txns[0] if txns else {}
    return client


async def test_get_transactions_with_trades():
    """Transactions are parsed with instrument details."""
    client = _mock_transactions_client(_mock_transactions_response())
    result = await get_transactions(client, "FAKE_HASH")

    assert "99001" in result
    assert "TRADE" in result
    assert "GLD_031826P480" in result
    assert "130.00" in result
    assert "99002" in result
    assert "DIVIDEND" in result
    assert "2 found" in result


async def test_get_transactions_empty():
    """Returns friendly message when no transactions exist."""
    client = AsyncMock()
    client.get_transactions.return_value = []
    result = await get_transactions(client, "FAKE_HASH")
    assert "No transactions found" in result


async def test_get_transaction_single():
    """Single transaction lookup returns formatted transaction."""
    client = _mock_transactions_client(_mock_transactions_response())
    result = await get_transaction(client, "FAKE_HASH", "99001")
    assert "99001" in result
    assert "TRADE" in result
