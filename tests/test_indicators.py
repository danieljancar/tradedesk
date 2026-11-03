from tradedesk.binance.market import floor_to, round_to
from tradedesk.indicators import Candle, atr, ema, rsi, swing_levels


def candle(i: int, low: float, high: float, close: float) -> Candle:
    return Candle(i, close, high, low, close, 1)


def test_rsi_extremes():
    assert rsi([float(i) for i in range(30)]) == 100.0
    assert rsi([float(30 - i) for i in range(30)]) < 1


def test_rsi_needs_enough_data():
    assert rsi([1.0, 2.0]) is None


def test_ema_of_flat_series_is_flat():
    assert ema([5.0] * 30, 10)[-1] == 5.0


def test_atr_of_constant_range():
    candles = [candle(i, 99, 101, 100) for i in range(30)]
    assert atr(candles) == 2


def test_swing_levels_split_around_price():
    prices = [100, 104, 108, 104, 100, 96, 92, 96, 100, 104, 100, 101, 100, 101]
    candles = [candle(i, p - 1, p + 1, p) for i, p in enumerate(prices)]
    support, resistance = swing_levels(candles, width=2)
    assert resistance == [105, 109]
    assert support[-1] == 91
    assert all(s < 100 for s in support)


def test_rounding_to_exchange_steps():
    assert floor_to(0.123456, 0.001) == 0.123
    assert floor_to(5.9, 1) == 5
    assert round_to(101.236, 0.01) == 101.24
