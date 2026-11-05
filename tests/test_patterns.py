from tradedesk.indicators import Candle
from tradedesk.patterns import find, name


def candles(highs, lows):
    return [
        Candle(i * 3_600_000, (h + lo) / 2, h, lo, (h + lo) / 2, 1.0)
        for i, (h, lo) in enumerate(zip(highs, lows, strict=True))
    ]


def wave(n, top, bottom, period=10):
    """Zig-zag between two lines; top and bottom are functions of the bar index."""
    out_h, out_l = [], []
    for i in range(n):
        phase = (i % period) / period
        mid = bottom(i) + (top(i) - bottom(i)) * (1 - abs(phase * 2 - 1))
        out_h.append(min(top(i), mid + 1))
        out_l.append(max(bottom(i), mid - 1))
    return candles(out_h, out_l)


def test_names_from_slopes():
    assert name(0, 0.1) == "ascending triangle"
    assert name(-0.1, 0) == "descending triangle"
    assert name(-0.1, 0.1) == "symmetrical triangle"
    assert name(0.1, 0.1) == "rising channel"
    assert name(-0.05, -0.2) == "falling channel"
    assert name(-0.3, -0.05) == "falling wedge"
    assert name(0.01, -0.01) == "range"


def test_finds_converging_lines():
    cs = wave(80, top=lambda i: 120 - i * 0.2, bottom=lambda i: 90 + i * 0.2)
    p = find(cs)
    assert p["pattern"] == "symmetrical triangle"
    assert p["upper"]["p2"] < p["upper"]["p1"] and p["lower"]["p2"] > p["lower"]["p1"]
    assert p["upper"]["t_end"] == cs[-1].open_time // 1000


def test_too_few_candles():
    assert find(candles([1, 2, 3], [0, 1, 2])) is None
