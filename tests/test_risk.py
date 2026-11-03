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
    v = check(idea(), settings, book(open_risk=35), price=100.5, atr=4, rules=RULES)
    assert any("open risk" in r for r in v.reasons)


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
