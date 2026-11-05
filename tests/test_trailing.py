import json

import pytest

from tradedesk.broker.paper import PaperBroker
from tradedesk.config import Trailing
from tradedesk.desk import Desk
from tradedesk.trailing import next_stop

CFG = Trailing()


def test_nothing_before_one_r():
    assert next_stop("long", 100, 95, 95, 104, 2, CFG) is None


def test_break_even_at_one_r():
    move = next_stop("long", 100, 95, 95, 105.5, 2, CFG)
    assert move.stop == pytest.approx(100.2)
    assert "break-even" in move.reason


def test_trails_atr_behind_price_from_one_and_a_half_r():
    move = next_stop("long", 100, 95, 100.2, 120, 2, CFG)
    assert move.stop == pytest.approx(116)
    assert "ATR behind price" in move.reason


def test_keeps_half_the_gain_when_atr_is_wide():
    move = next_stop("long", 100, 95, 100.2, 110, 6, CFG)
    assert move.stop == pytest.approx(105)
    assert "50% of the gain" in move.reason


def test_short_trails_down():
    move = next_stop("short", 100, 105, 105, 80, 2, CFG)
    assert move.stop == pytest.approx(84)


def test_never_moves_back_or_by_tiny_steps():
    assert next_stop("long", 100, 95, 116, 120, 2, CFG) is None
    assert next_stop("long", 100, 95, 115.8, 120, 2, CFG) is None


def test_stays_off_the_price():
    move = next_stop("long", 100, 95, 95, 108, 0.1, Trailing(trail_atr=0.1, lock_pct=99))
    assert move.stop < 108


def test_off_switch():
    assert next_stop("long", 100, 95, 95, 130, 2, Trailing(enabled=False)) is None


def plans_file(tmp_path):
    idea = dict(
        asset="BTC",
        horizon="mid",
        side="long",
        rating="buy",
        entry_type="market",
        entry=100,
        stop=94,
        take_profit=113,
        confidence=70,
        thesis="t",
        invalidation="i",
    )
    path = tmp_path / "plans.json"
    path.write_text(json.dumps({"market_view": "v", "ideas": [idea]}))
    return path


def test_sync_raises_the_stop_on_a_winner(settings, db, market, tmp_path, monkeypatch):
    desk = Desk(settings, db, PaperBroker(settings, market, db))
    desk.start_run()
    (desk.run_dir(desk.run_id()) / "facts.json").write_text(json.dumps({"BTC": {"atr_1d": 3}}))
    [r] = desk.check_plans(plans_file(tmp_path))
    desk.approve(r["id"])
    desk.execute()
    monkeypatch.setattr(Desk, "_atr", lambda self, symbol, horizon: 1.0)
    market.default = 110.0
    out = desk.sync()
    pos = db.open_positions()[0]
    assert pos["stop"] == pytest.approx(108)
    assert pos["initial_stop"] == 94
    assert any("stop raised" in line for line in out)
    assert not any("stop raised" in line for line in desk.sync())
