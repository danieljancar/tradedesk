from tradedesk.indicators import Candle
from tradedesk.patterns import find, levels, name


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


def test_index_closes_get_a_pattern():
    from datetime import date, timedelta

    from tradedesk.macro import _pack

    start = date(2026, 6, 1)
    pts = [
        ((start + timedelta(days=i)).isoformat(), 6000 + 40 * ((i % 10) - 5) * (1 - i / 200) + i)
        for i in range(140)
    ]
    d = _pack("SP500", "S&P 500", "Stocks", "", "", pts)
    assert d["pattern"] and d["pattern"]["pattern"]
    assert len(d["series"]) == 120
    assert _pack("VIXCLS", "VIX", "Risk", "", "", pts)["pattern"] is None


def test_levels_group_repeated_turns():
    # price turns at 100 and 120 again and again
    cs = wave(120, top=lambda i: 120, bottom=lambda i: 100, period=12)
    found = levels(cs, width=3)
    prices = sorted(round(x["price"]) for x in found[:2])
    assert prices == [100, 120]
    assert all(x["touches"] >= 2 for x in found)
    assert {x["kind"] for x in found[:2]} == {"support", "resistance"}
