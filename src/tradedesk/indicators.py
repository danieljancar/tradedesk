from collections.abc import Sequence
from dataclasses import dataclass
from itertools import pairwise


@dataclass(frozen=True)
class Candle:
    open_time: int
    open: float
    high: float
    low: float
    close: float
    volume: float

    @classmethod
    def from_binance(cls, row: Sequence) -> "Candle":
        return cls(int(row[0]), *(float(x) for x in row[1:6]))


def ema(values: Sequence[float], period: int) -> list[float]:
    if len(values) < period:
        return []
    k = 2 / (period + 1)
    out = [sum(values[:period]) / period]
    for v in values[period:]:
        out.append(v * k + out[-1] * (1 - k))
    return out


def rsi(closes: Sequence[float], period: int = 14) -> float | None:
    if len(closes) <= period:
        return None
    gains, losses = 0.0, 0.0
    for a, b in pairwise(closes[: period + 1]):
        d = b - a
        gains += max(d, 0)
        losses += max(-d, 0)
    avg_gain, avg_loss = gains / period, losses / period
    for a, b in pairwise(closes[period:]):
        d = b - a
        avg_gain = (avg_gain * (period - 1) + max(d, 0)) / period
        avg_loss = (avg_loss * (period - 1) + max(-d, 0)) / period
    if avg_loss == 0:
        return 100.0
    return 100 - 100 / (1 + avg_gain / avg_loss)


def atr(candles: Sequence[Candle], period: int = 14) -> float | None:
    if len(candles) <= period:
        return None
    trs = [
        max(c.high - c.low, abs(c.high - p.close), abs(c.low - p.close))
        for p, c in pairwise(candles)
    ]
    value = sum(trs[:period]) / period
    for tr in trs[period:]:
        value = (value * (period - 1) + tr) / period
    return value


def macd_hist(closes: Sequence[float]) -> float | None:
    fast, slow = ema(closes, 12), ema(closes, 26)
    if not slow:
        return None
    line = [f - s for f, s in zip(fast[-len(slow) :], slow, strict=True)]
    signal = ema(line, 9)
    return line[-1] - signal[-1] if signal else None


def swing_levels(candles: Sequence[Candle], width: int = 3, count: int = 3) -> tuple[list, list]:
    highs, lows = [], []
    for i in range(width, len(candles) - width):
        window = candles[i - width : i + width + 1]
        c = candles[i]
        if c.high == max(w.high for w in window):
            highs.append(c.high)
        if c.low == min(w.low for w in window):
            lows.append(c.low)
    price = candles[-1].close
    resistance = sorted(h for h in highs if h > price)[:count]
    support = sorted((lo for lo in lows if lo < price), reverse=True)[:count]
    return support, resistance


def pct(a: float, b: float) -> float:
    return (b - a) / a * 100 if a else 0.0
