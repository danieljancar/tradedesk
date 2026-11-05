import pytest
from pydantic import ValidationError

from tradedesk.config import Market
from tradedesk.models import TradeIdea
from tradedesk.risk import Book, check

from .conftest import RULES


def idea(**kw) -> TradeIdea:
    base = dict(
        asset="BTC",
        horizon="mid",
        side="long",
        rating="buy",
        entry=100,
        stop=95,
        take_profit=112,
        confidence=70,
        thesis="t",
        invalidation="i",
    )
    return TradeIdea(**(base | kw))


def book(**kw) -> Book:
    return Book(
        **(
            dict(
                equity=1000, free_quote=1000, peak_equity=1000, day_pnl=0, open_risk=0, open_count=0
            )
            | kw
        )
    )


def test_sizes_by_risk(settings):
    v = check(idea(), settings, book(), price=100.5, atr=4, rules=RULES)
    assert v.ok, v.reasons
    assert v.qty == 2.0
    assert v.risk_amount == pytest.approx(10)
    assert v.reward_risk == 2.4


def test_position_cap_limits_size(settings):
    v = check(idea(stop=99, take_profit=103), settings, book(), price=100.2, atr=0.5, rules=RULES)
    assert v.notional <= 250 + 1e-9


def test_rejects_low_reward(settings):
    v = check(idea(take_profit=105), settings, book(), price=100.5, atr=4, rules=RULES)
    assert not v.ok
    assert any("reward/risk" in r for r in v.reasons)


def test_rejects_short_on_spot(settings):
    v = check(
        idea(side="short", rating="sell", stop=105, take_profit=88),
        settings,
        book(),
        price=99.9,
        atr=4,
        rules=RULES,
    )
    assert any("futures" in r for r in v.reasons)


def test_allows_short_on_futures(settings):
    s = settings.model_copy(update={"market": Market.FUTURES})
    v = check(
        idea(side="short", rating="sell", stop=105, take_profit=88),
        s,
        book(),
        price=99.9,
        atr=4,
        rules=RULES,
    )
    assert v.ok, v.reasons


def test_rejects_stop_tighter_than_atr(settings):
    v = check(idea(stop=99.5, take_profit=102), settings, book(), price=100.1, atr=4, rules=RULES)
    assert any("ATR" in r for r in v.reasons)


def test_daily_loss_blocks_everything(settings):
    v = check(idea(), settings, book(day_pnl=-40), price=100.5, atr=4, rules=RULES)
    assert any("daily loss" in r for r in v.reasons)


def test_total_risk_cap(settings):
    v = check(idea(), settings, book(open_risk=36), price=100.5, atr=4, rules=RULES)
    assert any("open risk" in r for r in v.reasons)


def test_total_risk_cap_shrinks_a_trade_that_still_fits_half(settings):
    v = check(idea(), settings, book(open_risk=32), price=100.5, atr=4, rules=RULES)
    assert v.ok
    assert v.risk_amount == pytest.approx(8, abs=0.05)


def test_rejects_unknown_asset(settings):
    v = check(idea(asset="PEPE"), settings, book(), price=100.5, atr=4, rules=RULES)
    assert any("watchlist" in r for r in v.reasons)


def test_rejects_limit_entry_above_price(settings):
    v = check(
        idea(entry=103, stop=98, take_profit=115), settings, book(), price=100, atr=4, rules=RULES
    )
    assert any("past the current price" in r for r in v.reasons)


def test_model_rejects_stop_above_long_entry():
    with pytest.raises(ValidationError):
        idea(stop=101)


def test_futures_allows_one_trade_per_asset(settings):
    s = settings.model_copy(update={"market": Market.FUTURES})
    v = check(
        idea(horizon="short"), s, book(taken={("BTC", "mid")}), price=100.5, atr=4, rules=RULES
    )
    assert any("net per symbol" in r for r in v.reasons)


def test_no_equity_rejects():
    from tradedesk.config import Settings

    v = check(idea(), Settings(), book(equity=0), price=100.5, atr=4, rules=RULES)
    assert not v.ok


def test_house_money_risks_profits_at_their_own_rate(settings):
    from tradedesk.risk import position_risk

    settings.risk.principal = 100
    settings.risk.risk_per_trade_pct = 2
    settings.risk.profit_risk_pct = 10
    assert position_risk(settings, book(equity=100)) == pytest.approx(2.0)
    assert position_risk(settings, book(equity=150)) == pytest.approx(2.0 + 5.0)
    assert position_risk(settings, book(equity=80)) == pytest.approx(1.6)


def test_floor_shrinks_then_blocks_new_risk(settings):
    settings.risk.principal = 1000
    settings.risk.floor_pct = 99
    v = check(idea(), settings, book(open_risk=5), price=100.5, atr=4, rules=RULES)
    assert v.risk_amount <= 5.0 + 1e-6
    v = check(idea(), settings, book(open_risk=10), price=100.5, atr=4, rules=RULES)
    assert not v.ok and any("protected floor" in r for r in v.reasons)


def test_futures_stop_past_liquidation_is_rejected(settings):
    # big house-money risk on a small margin slot: the stop would sit past liquidation
    settings.market = Market.FUTURES
    settings.risk.max_leverage = 20
    settings.risk.max_position_pct = 100
    settings.risk.max_open_positions = 4
    settings.risk.principal = 13
    settings.risk.profit_risk_pct = 25
    settings.risk.max_total_risk_pct = 20
    v = check(
        idea(), settings, book(equity=200, free_quote=200), price=100.5, atr=None, rules=RULES
    )
    assert not v.ok and any("liquidated" in r for r in v.reasons)


def test_futures_leverage_uses_margin_slot(settings):
    settings.market = Market.FUTURES
    settings.risk.max_leverage = 10
    settings.risk.max_position_pct = 100
    settings.risk.max_open_positions = 4
    v = check(idea(stop=98, take_profit=106), settings, book(), price=100.5, atr=None, rules=RULES)
    assert v.ok, v.reasons
    assert v.qty * v.entry / v.leverage <= 1000 / 4 + 1e-6


def test_conviction_scales_risk_with_confidence(settings):
    from tradedesk.risk import position_risk

    settings.risk.risk_per_trade_pct = 2
    settings.risk.min_confidence = 60
    settings.risk.confident_at = 80
    settings.risk.confident_risk_x = 2
    assert position_risk(settings, book(equity=100), 60) == pytest.approx(2.0)
    assert position_risk(settings, book(equity=100), 70) == pytest.approx(3.0)
    assert position_risk(settings, book(equity=100), 95) == pytest.approx(4.0)
    assert position_risk(settings, book(equity=100)) == pytest.approx(2.0)


def test_conviction_still_bounded_by_total_risk(settings):
    settings.risk.confident_risk_x = 3
    settings.risk.max_total_risk_pct = 2
    v = check(idea(confidence=95), settings, book(), price=100.5, atr=4, rules=RULES)
    assert v.risk_amount <= 20 + 1e-6


def test_spot_exit_outside_the_price_band_is_refused(settings):
    from tradedesk.binance.market import SymbolRules

    tight = SymbolRules(tick=0.01, step=0.0001, min_qty=0.0001, min_notional=5, sell_down=0.97)
    v = check(idea(), settings, book(), price=100.5, atr=4, rules=tight)
    assert any("lowest sell price" in r for r in v.reasons)
