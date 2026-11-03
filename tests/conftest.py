from datetime import UTC, datetime

import pytest

from tradedesk.binance.market import SymbolRules
from tradedesk.config import Settings
from tradedesk.db import Database
from tradedesk.indicators import Candle

RULES = SymbolRules(tick=0.01, step=0.0001, min_qty=0.0001, min_notional=5)


class FakeMarket:
    def __init__(self, price: float = 100.0):
        self.prices: dict[str, float] = {}
        self.default = price
        self.candles: list[Candle] = []

    def price(self, symbol: str) -> float:
        return self.prices.get(symbol, self.default)

    def rules(self, symbol: str) -> SymbolRules:
        return RULES

    def klines(self, symbol, interval, limit=200, start_ms=None):
        return [c for c in self.candles if start_ms is None or c.open_time >= start_ms - 3_600_000]

    def add(self, low: float, high: float, close: float | None = None) -> None:
        t = int(datetime.now(UTC).timestamp() * 1000) + len(self.candles) * 3_600_000
        close = close if close is not None else (low + high) / 2
        self.candles.append(Candle(t, close, high, low, close, 1.0))


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        watchlist=["BTC", "ETH"],
        paper_equity=1000,
        db_path=tmp_path / "d.db",
        runs_dir=tmp_path / "runs",
    )


@pytest.fixture
def db(settings) -> Database:
    return Database(settings.db_path)


@pytest.fixture
def market() -> FakeMarket:
    return FakeMarket()


@pytest.fixture(autouse=True)
def offline(monkeypatch, market) -> None:
    """The desk reads public candles through market_data; tests feed it the FakeMarket."""
    monkeypatch.setattr("tradedesk.desk.market_data", lambda *a, **k: market)
