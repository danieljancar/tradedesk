"""Chart patterns from swing points: a trendline through the last two swing highs and one
through the last two swing lows, and what their slopes make together. Plain geometry, so the
dashboard can draw them and the analysts can read them without spending tokens."""

from collections.abc import Sequence

from tradedesk.indicators import Candle, atr


def pivots(candles: Sequence[Candle], width: int = 3) -> tuple[list, list]:
    highs, lows = [], []
    for i in range(width, len(candles) - width):
        window = candles[i - width : i + width + 1]
        c = candles[i]
        if c.high == max(w.high for w in window):
            highs.append((i, c.open_time, c.high))
        if c.low == min(w.low for w in window):
            lows.append((i, c.open_time, c.low))
    return highs, lows


def _line(a: tuple, b: tuple) -> dict:
    return {"t1": a[1] // 1000, "p1": a[2], "t2": b[1] // 1000, "p2": b[2], "i1": a[0], "i2": b[0]}


def at(line: dict, index: int) -> float:
    return line["p1"] + (line["p2"] - line["p1"]) * (index - line["i1"]) / (line["i2"] - line["i1"])


def name(upper: float, lower: float) -> str:
    """Slopes in ATRs per bar. Under 0.02 counts as flat."""
    flat = 0.02
    up_f, lo_f = abs(upper) < flat, abs(lower) < flat
    if up_f and lo_f:
        return "range"
    if up_f and lower > 0:
        return "ascending triangle"
    if lo_f and upper < 0:
        return "descending triangle"
    if upper < 0 < lower:
        return "symmetrical triangle"
    if upper > 0 > lower:
        return "broadening"
    if upper > 0 and lower > 0:
        return "rising wedge" if lower > upper * 1.3 else "rising channel"
    if upper < 0 and lower < 0:
        return "falling wedge" if upper < lower * 1.3 else "falling channel"
    return "range"


def find(candles: Sequence[Candle], lookback: int = 120, width: int = 3) -> dict | None:
    recent = list(candles[-lookback:])
    if len(recent) < 2 * width + 10:
        return None
    highs, lows = pivots(recent, width)
    if len(highs) < 2 or len(lows) < 2:
        return None
    a = atr(recent) or 0
    if not a:
        return None
    upper, lower = _line(highs[-2], highs[-1]), _line(lows[-2], lows[-1])
    last = len(recent) - 1

    def slope(line: dict) -> float:
        return (line["p2"] - line["p1"]) / (line["i2"] - line["i1"]) / a

    top, bottom, close = at(upper, last), at(lower, last), recent[-1].close
    if close > top:
        position = "broke above the upper line"
    elif close < bottom:
        position = "broke below the lower line"
    else:
        position = "inside"
    end = recent[-1].open_time // 1000
    return {
        "pattern": name(slope(upper), slope(lower)),
        "position": position,
        "upper": {**upper, "t_end": end, "p_end": top},
        "lower": {**lower, "t_end": end, "p_end": bottom},
    }


def line(frame: str, p: dict | None, num) -> str:
    if not p:
        return f"pattern {frame}: none clear"
    u, lo = p["upper"], p["lower"]
    return (
        f"pattern {frame}: {p['pattern']}, upper line {num(u['p1'])} to {num(u['p2'])} "
        f"(now {num(u['p_end'])}), lower line {num(lo['p1'])} to {num(lo['p2'])} "
        f"(now {num(lo['p_end'])}), price {p['position']}"
    )


# timeframe, bars to look back, swing width
SCALES = {"short": ("4h", 120, 3), "mid": ("1d", 240, 5), "long": ("1w", 260, 4)}


def levels(candles: Sequence[Candle], width: int = 4, keep: int = 6) -> list[dict]:
    """Horizontal levels the price turned at more than once, strongest first. Swing points
    within half an ATR of each other count as the same level."""
    highs, lows = pivots(candles, width)
    a = atr(candles) or 0
    if not a:
        return []
    points = sorted([(p, t) for _, t, p in highs] + [(p, t) for _, t, p in lows])
    groups: list[list[tuple[float, int]]] = []
    for price, t in points:
        if groups and price - groups[-1][-1][0] <= a / 2:
            groups[-1].append((price, t))
        else:
            groups.append([(price, t)])
    close = candles[-1].close
    out = []
    for g in groups:
        if len(g) < 2:
            continue
        price = sum(x for x, _ in g) / len(g)
        out.append(
            {
                "price": price,
                "touches": len(g),
                "since": min(t for _, t in g) // 1000,
                "kind": "support" if price < close else "resistance",
            }
        )
    return sorted(out, key=lambda x: (-x["touches"], abs(x["price"] - close)))[:keep]
