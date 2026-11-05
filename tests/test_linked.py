import json

import pytest

from tradedesk import transfers
from tradedesk.broker.paper import PaperBroker
from tradedesk.config import Market, Settings, Transfers, linked_settings
from tradedesk.db import Database
from tradedesk.desk import Desk


def idea(asset, side, **kw):
    long = side == "long"
    return (
        dict(
            asset=asset,
            horizon="mid",
            side=side,
            rating="buy" if long else "sell",
            entry_type="market",
            entry=100,
            stop=94 if long else 106,
            take_profit=113 if long else 87,
            confidence=70,
            thesis="t",
            invalidation="i",
        )
        | kw
    )


@pytest.fixture
def pair(settings, db, market, tmp_path):
    fs = Settings(
        market=Market.FUTURES,
        watchlist=settings.watchlist,
        paper_equity=500,
        db_path=tmp_path / "f.db",
        runs_dir=settings.runs_dir,
    )
    fdb = Database(fs.db_path)
    main = Desk(settings, db, PaperBroker(settings, market, db))
    main.link(Desk(fs, fdb, PaperBroker(fs, market, fdb)))
    main.start_run()
    return main


def check(desk, tmp_path, *ideas, actions=()):
    path = tmp_path / "plans.json"
    path.write_text(
        json.dumps({"market_view": "v", "ideas": list(ideas), "position_actions": list(actions)})
    )
    return desk.check_plans(path)


def test_ideas_go_to_their_wallet(pair, tmp_path):
    results = check(
        pair,
        tmp_path,
        idea("BTC", "long"),
        idea("ETH", "short"),
        idea("ETH", "long", venue="futures", horizon="short"),
    )
    assert [r["venue"] for r in results] == ["spot", "futures", "futures"]
    assert results[0]["status"] == "proposed" and results[1]["status"] == "proposed"
    assert "futures net per symbol" in results[2]["reasons"][0]
    assert len(pair.db.all("SELECT id FROM plans")) == 1
    assert len(pair.linked.db.all("SELECT id FROM plans")) == 2


def test_futures_events_land_on_the_main_floor(pair, tmp_path):
    check(pair, tmp_path, idea("ETH", "short"))
    titles = [e["title"] for e in pair.db.events(pair.run_id())]
    assert any(t.startswith("Futures: Passed: ETH short") for t in titles)
    assert pair.linked.db.events(pair.run_id()) == []


def test_execute_and_sync_cover_both_wallets(pair, tmp_path):
    [spot, fut] = check(pair, tmp_path, idea("BTC", "long"), idea("ETH", "short"))
    pair.approve(spot["id"])
    pair.linked.approve(fut["id"])
    out = pair.execute()
    assert any(line.startswith("futures: ") for line in out)
    assert len(pair.db.open_positions()) == 1
    assert pair.linked.db.open_positions()[0]["side"] == "short"
    pair.sync()
    assert pair.linked.db.all("SELECT * FROM equity")


def test_futures_position_action_reaches_the_futures_book(pair, tmp_path):
    [fut] = check(pair, tmp_path, idea("ETH", "short"))
    pair.linked.approve(fut["id"])
    pair.execute()
    pos = pair.linked.db.open_positions()[0]
    action = {"position_id": pos["id"], "action": "close", "reason": "r", "venue": "futures"}
    [r] = check(pair, tmp_path, actions=[action])
    assert r["status"] == "closed" and r["venue"] == "futures"


def test_book_shows_the_futures_wallet(pair):
    text = pair.write_book().read_text()
    assert "## Futures wallet" in text
    assert "equity 500.00" in text


def test_transfer_plan_moves_free_money_toward_the_target():
    cfg = Transfers(enabled=True, futures_pct=35, band_pct=10, min_amount=5, keep_free_pct=10)
    assert transfers.plan(190, 0, 190, 0, cfg) == pytest.approx(66.5)
    assert transfers.plan(120, 70, 120, 70, cfg) == 0
    assert transfers.plan(100, 100, 100, 40, cfg) == pytest.approx(-30)
    assert transfers.plan(190, 0, 22, 0, cfg) == 0


def test_paper_transfer_moves_equity_without_a_drawdown(pair):
    pair.settings.transfers = Transfers(enabled=True, futures_pct=50, band_pct=5)
    pair.settings.risk.principal = 1000
    pair.linked.settings.risk.principal = 500
    before = pair.book().equity
    pair.db.record_equity(before)
    out = transfers.balance(pair, pair.linked)
    assert out and "spot to futures" in out[0]
    assert pair.book().equity == pytest.approx(750)
    assert pair.linked.book().equity == pytest.approx(750)
    assert pair.book().peak_equity == pytest.approx(750)
    assert pair.book().principal == pytest.approx(750)
    assert transfers.balance(pair, pair.linked) == []


def test_linked_settings_follow_the_main_desk(tmp_path):
    f = tmp_path / "f.toml"
    f.write_text('market = "spot"\ndb_path = "data/f.db"\n[risk]\nmax_leverage = 10\n')
    main = Settings(futures_desk=f, runs_dir=tmp_path / "runs", watchlist=["BTC"])
    fs = linked_settings(main)
    assert fs.market is Market.FUTURES and fs.runs_dir == main.runs_dir
    assert fs.risk.max_leverage == 10 and fs.watchlist == ["BTC"]


def test_local_errors_keep_a_futures_entry_waiting(pair, tmp_path, monkeypatch):
    from tradedesk.binance.client import BinanceError

    fut = pair.linked
    [r] = check(
        pair,
        tmp_path,
        idea("ETH", "short", entry_type="limit", entry=101, stop=107, take_profit=88),
    )
    fut.approve(r["id"])
    fut.db.update("plans", r["id"], status="placed")

    def broken(plan):
        raise FileNotFoundError(2, "No such file or directory")

    monkeypatch.setattr(fut, "_sync_entry", broken)
    fut.sync()
    assert fut.db.one("SELECT status FROM plans")["status"] == "placed"

    def refused(plan):
        raise BinanceError(400, -2019, "Margin is insufficient")

    monkeypatch.setattr(fut, "_sync_entry", refused)
    fut.sync()
    assert fut.db.one("SELECT status FROM plans")["status"] == "rejected"


def test_samples_before_a_transfer_are_not_a_drawdown(pair):
    pair.db.record_equity(1000, "2026-11-05T22:00:00+00:00")
    pair.db.record_flow(-350, "transfer", ts="2026-11-05T22:00:01+00:00")
    pair.db.record_equity(650, "2026-11-05T22:00:01+00:00")
    pair.db.record_equity(640, "2026-11-05T22:10:00+00:00")
    assert pair.db.peak_equity() == pytest.approx(650)
