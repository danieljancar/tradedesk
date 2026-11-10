import json

import pytest

from tradedesk.broker.paper import PaperBroker
from tradedesk.desk import Desk


def plans_file(tmp_path, **kw):
    idea = dict(
        asset="BTC",
        horizon="mid",
        side="long",
        rating="buy",
        entry_type="limit",
        entry=99,
        stop=94,
        take_profit=111,
        confidence=70,
        thesis="t",
        invalidation="i",
    )
    path = tmp_path / "plans.json"
    path.write_text(json.dumps({"market_view": "v", "ideas": [idea | kw]}))
    return path


def make_desk(settings, db, market):
    desk = Desk(settings, db, PaperBroker(settings, market, db))
    desk.start_run()
    (desk.run_dir(desk.run_id()) / "facts.json").write_text(json.dumps({"BTC": {"atr_1d": 3}}))
    return desk


def test_limit_entry_then_stop(settings, db, market, tmp_path):
    desk = make_desk(settings, db, market)
    [result] = desk.check_plans(plans_file(tmp_path))
    assert result["status"] == "proposed", result
    desk.approve(result["id"])
    assert "resting" in desk.execute()[0]

    market.add(low=98.5, high=100.5)
    assert "filled" in desk.sync()[0]
    market.add(low=93, high=99)
    assert "stop" in desk.sync()[0]

    [pos] = db.all("SELECT * FROM positions")
    assert pos["status"] == "closed"
    assert pos["pnl"] < 0
    assert abs(pos["pnl"] + 10) < 1


def test_market_entry_hits_target(settings, db, market, tmp_path):
    desk = make_desk(settings, db, market)
    [result] = desk.check_plans(
        plans_file(tmp_path, entry_type="market", entry=100, take_profit=113)
    )
    desk.approve(result["id"])
    desk.execute()
    market.add(low=99, high=114)
    desk.sync()
    [pos] = db.all("SELECT * FROM positions")
    assert pos["exit_reason"] == "target"
    assert pos["pnl"] > 0


def test_auto_execute_only_approves_passing_plans(settings, db, market, tmp_path):
    settings.execution.auto_execute = True
    desk = make_desk(settings, db, market)
    [bad] = desk.check_plans(plans_file(tmp_path, take_profit=101))
    assert bad["status"] == "rejected"
    assert db.one("SELECT status FROM plans")["status"] == "rejected"


def test_stop_only_moves_forward(settings, db, market, tmp_path):
    desk = make_desk(settings, db, market)
    [r] = desk.check_plans(plans_file(tmp_path, entry_type="market", entry=100, take_profit=113))
    desk.approve(r["id"])
    desk.execute()
    assert desk.tighten(1, 90)["status"] == "rejected"
    assert desk.tighten(1, 97)["status"] == "tightened"


def test_events_trace_the_run(settings, db, market, tmp_path):
    desk = make_desk(settings, db, market)
    desk.check_plans(plans_file(tmp_path))
    actors = [e["actor"] for e in db.events(desk.run_id())]
    assert actors[0] == "desk"
    assert "risk" in actors


def test_kill_cancels_and_flattens(settings, db, market, tmp_path):
    desk = make_desk(settings, db, market)
    [r] = desk.check_plans(plans_file(tmp_path, entry_type="market", entry=100, take_profit=113))
    desk.approve(r["id"])
    desk.execute()
    desk.kill(flatten=True)
    assert db.open_positions() == []


def test_entry_cancelled_when_target_comes_first(settings, db, market, tmp_path):
    desk = make_desk(settings, db, market)
    [result] = desk.check_plans(plans_file(tmp_path))
    desk.approve(result["id"])
    desk.execute()
    market.add(low=101, high=112)
    market.prices["BTCUSDT"] = 112
    assert "target before the entry" in desk.sync()[0]
    assert db.all("SELECT status FROM plans")[0]["status"] == "expired"
    assert db.all("SELECT * FROM positions") == []


def test_entries_only_checks_waiting_plans(settings, db, market, tmp_path):
    desk = make_desk(settings, db, market)
    [result] = desk.check_plans(plans_file(tmp_path))
    desk.approve(result["id"])
    desk.execute()
    market.add(low=98.5, high=100.5)
    assert "filled" in desk.entries()[0]
    assert desk.entries() == []


def test_precheck_records_nothing(settings, db, market, tmp_path):
    desk = make_desk(settings, db, market)
    [r] = desk.preview_plans(plans_file(tmp_path))
    assert r["ok"] and r["qty"] > 0
    assert db.all("SELECT * FROM plans") == []


def test_banks_half_at_one_r_and_counts_it_in_the_result(settings, db, market, tmp_path):
    desk = make_desk(settings, db, market)
    [r] = desk.check_plans(plans_file(tmp_path, entry_type="market", entry=100, take_profit=113))
    desk.approve(r["id"])
    desk.execute()
    pos = db.one("SELECT * FROM positions")
    one_r = pos["entry_price"] + (pos["entry_price"] - pos["initial_stop"])
    market.prices["BTCUSDT"] = one_r + 0.1
    assert any("banked" in line for line in desk.sync())
    after = db.one("SELECT * FROM positions")
    assert after["qty"] == pytest.approx(pos["qty"] / 2) and after["banked"] > 0
    assert not any("banked" in line for line in desk.sync())
    desk.close(after["id"], "manual")
    closed = db.one("SELECT * FROM positions")
    assert closed["pnl"] > after["banked"]


def test_wakeups_fire_once_when_due(settings, db, market):
    from datetime import UTC, datetime, timedelta

    desk = make_desk(settings, db, market)
    assert "passed" in desk.wake(datetime.now(UTC) - timedelta(minutes=1), "late")
    assert "scheduled" in desk.wake(datetime.now(UTC) + timedelta(hours=1), "CPI")
    assert desk.due_wakeups() == []
    db.conn.execute("UPDATE wakeups SET at = '2000-01-01T00:00:00+00:00'")
    assert [w["note"] for w in desk.due_wakeups()] == ["CPI"]
    assert desk.due_wakeups() == []
