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
    monkeypatch.setattr(snapshot, "sentiment", lambda: ("fear & greed: not available", {}))
    text, facts = snapshot.build(settings, TrendMarket())
    assert "## BTCUSDT" in text and "## ETHUSDT" in text
    assert "not a measured zero" in text
    assert facts["BTC"]["atr_1d"] > 0
    assert facts["BTC"]["frames"]["1d"]["rsi"] is not None
    assert facts["BTC"]["derivatives"] is None
    assert len(text.split()) < 600


def test_headline_image_and_summary_come_from_the_feed():
    import feedparser

    from tradedesk.wire import image, summary

    feed = feedparser.parse(
        '<rss xmlns:media="http://search.yahoo.com/mrss/"><channel>'
        '<item><title>T</title><media:content url="https://img/a.jpg" medium="image"/>'
        "<description>&lt;p&gt;Hello &lt;b&gt;world&lt;/b&gt;&lt;/p&gt;</description></item>"
        '<item><title>U</title><description>&lt;img src="https://img/b.png"&gt; text'
        "</description></item></channel></rss>"
    )
    assert [image(e) for e in feed.entries] == ["https://img/a.jpg", "https://img/b.png"]
    assert [summary(e) for e in feed.entries] == ["Hello world", "text"]
