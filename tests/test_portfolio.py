import pytest

from tradedesk import portfolio
from tradedesk.binance.market import SymbolRules
from tradedesk.broker.paper import PaperBroker
from tradedesk.config import Market, Portfolio
from tradedesk.db import Database, now
from tradedesk.desk import Desk
from tradedesk.risk import Book, check

from .conftest import RULES
from .test_risk import idea


@pytest.fixture
def core(settings):
    settings.portfolio = Portfolio(core_pct=50, core_targets={"BTC": 60, "PAXG": 40})
    return settings


def lot(id_, qty, day, asset="BTC"):
    return {"id": id_, "asset": asset, "qty": qty, "opened_at": f"2026-10-{day:02d}T00:00:00"}


def run(settings, holdings, rules=RULES, prices=None):
    prices = prices or {"BTC": 100.0, "PAXG": 50.0}
    rows = portfolio.rebalance(settings, holdings, 1000, prices, dict.fromkeys(prices, rules))
    return {r["asset"]: r for r in rows}


def test_under_target_buys_the_gap(core):
    rows = run(core, [])
    assert rows["BTC"]["target"] == 300 and rows["BTC"]["action"] == "buy"
    assert rows["BTC"]["qty"] == 3.0
    assert rows["PAXG"]["qty"] == 4.0 and rows["PAXG"]["amount"] == 200


def test_within_band_holds(core):
    rows = run(core, [lot(1, 2.9, 1), lot(2, 4.1, 1, "PAXG")])
    assert rows["BTC"]["drift_pct"] == pytest.approx(-3.33, abs=0.01)
    assert {r["action"] for r in rows.values()} == {"hold"}


def test_over_target_sells_newest_lots_that_fit(core):
    rows = run(core, [lot(1, 1.0, 2), lot(2, 0.5, 5), lot(3, 2.0, 1)])
    btc = rows["BTC"]
    assert btc["value"] == 350 and btc["action"] == "trim"
    assert btc["lots"] == [2] and btc["amount"] == 50


def test_over_target_never_goes_under(core):
    rows = run(core, [lot(1, 1.5, 1), lot(2, 2.0, 5)])
    assert rows["BTC"]["action"] == "hold"
    assert "under target" in rows["BTC"]["note"]


def test_exchange_minimum_blocks_small_buys(core):
    rules = SymbolRules(tick=0.01, step=0.0001, min_qty=0.0001, min_notional=50)
    rows = run(core, [lot(1, 2.8, 1), lot(2, 4.0, 1, "PAXG")], rules)
    assert rows["BTC"]["action"] == "hold"
    assert "minimum" in rows["BTC"]["note"]


def test_core_off_and_removed_assets(core):
    rows = run(core, [lot(1, 1.0, 1, "ETH")], prices={"BTC": 100.0, "PAXG": 50.0, "ETH": 10.0})
    assert rows["ETH"]["weight"] == 0 and rows["ETH"]["action"] == "trim"
    core.portfolio = Portfolio()
    assert run(core, [lot(1, 1.0, 1)]) == {}


def test_active_sizing_uses_the_sleeve(settings):
    base = dict(equity=1000, free_quote=1000, peak_equity=1000, day_pnl=0)
    v = check(
        idea(),
        settings,
        Book(**base, open_risk=0, open_count=0, sleeve_equity=500),
        100.5,
        4,
        RULES,
    )
    assert v.ok and v.risk_amount == pytest.approx(5)
    v = check(
        idea(),
        settings,
        Book(**base, open_count=0, open_risk=18, sleeve_equity=500),
        100.5,
        4,
        RULES,
    )
    assert any("open risk" in r for r in v.reasons)
    paused = Book(**{**base, "peak_equity": 1200}, open_risk=0, open_count=0, sleeve_equity=500)
    assert any("drawdown" in r for r in check(idea(), settings, paused, 100.5, 4, RULES).reasons)


def make_desk(settings, market) -> Desk:
    db = Database(settings.db_path)
    desk = Desk(settings, db, PaperBroker(settings, market, db))
    desk.start_run()
    return desk


def test_core_plans_skip_trade_rules_and_stay_out_of_the_active_book(core, market):
    core.risk.min_confidence = 100
    desk = make_desk(core, market)
    r = desk.rebalance(propose=True)
    assert [p["status"] for p in r["plans"]] == ["proposed", "proposed"]
    paxg = desk.db.one("SELECT * FROM plans WHERE asset = 'PAXG'")
    assert paxg["sleeve"] == "core" and paxg["horizon"] == "long" and paxg["confidence"] == 100
    assert paxg["stop"] == 65 and paxg["take_profit"] == 190
    assert (desk.run_dir(desk.run_id()) / "rebalance.md").exists()
    for p in r["plans"]:
        desk.approve(p["id"])
    desk.execute()
    positions = desk.db.open_positions()
    assert {p["sleeve"] for p in positions} == {"core"} and len(positions) == 2
    book = desk.book()
    assert book.open_count == 0 and book.open_risk == 0 and book.taken == set()
    assert book.sleeve_equity == pytest.approx(book.equity / 2)
    assert desk.rebalance(propose=True)["plans"] == []
    text = desk.write_book().read_text()
    assert "## Core" in text and "closed active trades" in text


def test_core_buys_still_respect_pause_futures_and_cash(core, market):
    desk = make_desk(core, market)
    desk.db.conn.execute("INSERT INTO equity (ts, value) VALUES ('2026-10-01T00:00:00', 2000)")
    desk.db.conn.commit()
    assert all("paused" in p["reasons"][0] for p in desk.rebalance(propose=True)["plans"])
    core.market = Market.FUTURES
    desk.db.conn.execute("DELETE FROM equity")
    plans = desk.rebalance(propose=True)["plans"]
    assert all(p["status"] == "rejected" for p in plans)
    assert desk.db.one("SELECT COUNT(*) AS n FROM plans WHERE status = 'proposed'")["n"] == 0


def test_trims_wait_for_approval_then_sell(core, market):
    market.prices["PAXGUSDT"] = 50
    desk = make_desk(core, market)
    for qty, day in ((1.0, 2), (0.5, 5), (2.0, 1)):
        desk.db.insert(
            "positions",
            symbol="BTCUSDT",
            asset="BTC",
            horizon="long",
            side="long",
            qty=qty,
            entry_price=100,
            stop=65,
            take_profit=190,
            initial_stop=65,
            opened_at=f"2026-10-{day:02d}T00:00:00+00:00",
            sleeve="core",
        )
    desk.db.insert(
        "positions",
        symbol="PAXGUSDT",
        asset="PAXG",
        horizon="long",
        side="long",
        qty=4,
        entry_price=50,
        stop=30,
        take_profit=95,
        initial_stop=30,
        opened_at=now(),
        sleeve="core",
    )
    r = desk.rebalance(propose=True)
    [t] = r["trims"]
    assert desk.db.one("SELECT status FROM trims WHERE id = ?", t["id"])["status"] == "proposed"
    assert desk.execute() == []
    portfolio.approve_trim(desk, t["id"])
    assert "sold" in desk.execute()[0]
    pos = desk.db.one("SELECT * FROM positions WHERE id = ?", t["position"])
    assert pos["status"] == "closed" and pos["qty"] == 0.5
    with pytest.raises(ValueError):
        portfolio.approve_trim(desk, t["id"])


def test_auto_execute_approves_core_plans(core, market):
    core.execution.auto_execute = True
    desk = make_desk(core, market)
    desk.rebalance(propose=True)
    assert {p["status"] for p in desk.db.all("SELECT status FROM plans")} == {"approved"}


def test_core_positions_do_not_expire(core, market):
    desk = make_desk(core, market)
    desk.db.insert(
        "positions",
        symbol="BTCUSDT",
        asset="BTC",
        horizon="long",
        side="long",
        qty=1,
        entry_price=100,
        stop=65,
        take_profit=190,
        initial_stop=65,
        opened_at="2020-01-01T00:00:00+00:00",
        sleeve="core",
        plan_id=None,
    )
    assert desk.sync() == []
    assert len(desk.db.open_positions()) == 1


def test_migration_adds_sleeve_to_old_databases(tmp_path):
    path = tmp_path / "old.db"
    old = Database(path)
    old.insert("plans", **PLAN)
    with old.tx() as c:
        c.execute("ALTER TABLE plans DROP COLUMN sleeve")
    db = Database(path)
    Database(path)
    assert db.one("SELECT sleeve FROM plans")["sleeve"] == "active"


PLAN = dict(
    asset="BTC",
    symbol="BTCUSDT",
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
    status="proposed",
    created_at="2026-10-01T00:00:00",
    updated_at="2026-10-01T00:00:00",
)
