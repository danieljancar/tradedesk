import math

from tradedesk import snapshot
from tradedesk.indicators import Candle

from .conftest import FakeMarket


class TrendMarket(FakeMarket):
    def klines(self, symbol, interval, limit=200, start_ms=None):
        out = []
        for i in range(limit):
            close = 100 + i * 0.5 + 3 * math.sin(i / 4)
            out.append(Candle(i, close - 0.5, close + 1.5, close - 1.5, close, 10 + i % 7))
        return out

    def derivatives(self, symbol):
        return None


def test_snapshot_is_compact_and_flags_missing_data(settings, monkeypatch):
    monkeypatch.setattr(snapshot, "sentiment", lambda: "fear & greed: not available")
    text, facts = snapshot.build(settings, TrendMarket())
    assert "## BTCUSDT" in text and "## ETHUSDT" in text
    assert "not a measured zero" in text
    assert facts["BTC"]["atr_1d"] > 0
    assert len(text.split()) < 600
