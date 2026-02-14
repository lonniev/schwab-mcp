"""Pydantic models for structured Schwab API responses."""

from datetime import date
from typing import Literal

from pydantic import BaseModel


class OptionPosition(BaseModel):
    symbol: str
    underlying: str
    put_call: Literal["PUT", "CALL"]
    strike: float
    expiration: date
    dte: int
    quantity: int
    avg_price: float
    market_value: float
    unrealized_pl: float


class SpreadPosition(BaseModel):
    underlying: str
    spread_type: str  # "Bull Put Spread", "Bear Call Spread"
    short_leg: OptionPosition
    long_leg: OptionPosition
    credit_received: float
    max_loss: float
    current_value: float
    unrealized_pl: float


class EquityPosition(BaseModel):
    symbol: str
    quantity: float
    avg_cost: float
    current_price: float
    market_value: float
    unrealized_pl: float


class AccountBalances(BaseModel):
    cash_balance: float
    buying_power: float
    net_liquidation: float
    day_pl: float


class Quote(BaseModel):
    symbol: str
    last_price: float
    bid: float
    ask: float
    volume: int
    change_pct: float
    high_52wk: float
    low_52wk: float


class OptionContract(BaseModel):
    symbol: str
    strike: float
    expiration: date
    dte: int
    put_call: Literal["PUT", "CALL"]
    bid: float
    ask: float
    last: float
    volume: int
    open_interest: int
    implied_volatility: float
    delta: float
    gamma: float
    theta: float
    otm_pct: float


class Candle(BaseModel):
    datetime_ms: int
    open: float
    high: float
    low: float
    close: float
    volume: int
