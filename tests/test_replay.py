from datetime import UTC, datetime

from tradedesk.indicators import Candle
from tradedesk.replay import replay

T0 = datetime(2026, 11, 3, 22, tzinfo=UTC)
H = 3_600_000
START = int(T0.timestamp() * 1000)


def candles(*bars):
    return [Candle(START + i * H, o, h, lo, c, 1.0) for i, (o, h, lo, c) in enumerate(bars)]


def plan(**kw):
    base = dict(
        side="long",
        entry_type="limit",
        entry=100.0,
        stop=95.0,
        take_profit=110.0,
        created_at=T0.isoformat(),
    )
    return base | kw


def test_limit_long_fills_then_hits_target():
    out = replay(plan(), candles((103, 104, 101, 102), (102, 102, 99, 100), (100, 111, 100, 110)))
    assert out["outcome"] == "target" and out["r"] == 2.0


def test_stop_wins_when_both_hit_in_one_candle():
    out = replay(plan(), candles((101, 101, 99, 100), (100, 112, 94, 100)))
    assert out["outcome"] == "stop" and out["r"] == -1.0


def test_unfilled_limit_waits_then_expires():
    bars = [(105, 106, 104, 105)] * 3
    assert replay(plan(), candles(*bars))["outcome"] == "waiting"
    assert replay(plan(), candles(*bars), entry_ttl_hours=1)["outcome"] == "expired"


def test_short_market_entry_marks_open_r():
    out = replay(
        plan(side="short", entry_type="market", entry=100, stop=105, take_profit=90),
        candles((100, 101, 98, 99), (99, 100, 97, 97.5)),
    )
    assert out["outcome"] == "open" and out["r"] == 0.5
