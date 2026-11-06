import json

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
