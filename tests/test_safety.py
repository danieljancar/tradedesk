import json
import tomllib
from datetime import UTC, datetime, timedelta

import httpx
import pytest
import respx
from pydantic import ValidationError

from tradedesk import analytics, portfolio, settings_io
from tradedesk.binance.client import Client
from tradedesk.broker.base import CloseFailed
from tradedesk.broker.paper import PaperBroker
from tradedesk.broker.spot import SpotBroker
from tradedesk.config import Market, Portfolio, RiskLimits, Settings
from tradedesk.db import Database, now
from tradedesk.desk import CORE_ACTION, Desk

from .conftest import FakeMarket
from .test_exchange import SPOT, params
from .test_paper_flow import plans_file

OCO = {
    "orderListId": 9,
    "orderReports": [{"type": "LIMIT_MAKER", "orderId": 2}, {"type": "STOP_LOSS", "orderId": 3}],
}


def make_desk(settings, market, broker=None) -> Desk:
    db = Database(settings.db_path)
    desk = Desk(settings, db, broker or PaperBroker(settings, market, db))
    desk.start_run()
    (desk.run_dir(desk.run_id()) / "facts.json").write_text(json.dumps({"BTC": {"atr_1d": 3}}))
    return desk


def add_position(db, asset="BTC", qty=1.0, sleeve="core", opened="2026-10-01T00:00:00+00:00"):
    return db.insert(
        "positions",
        symbol=f"{asset}USDT",
        asset=asset,
        horizon="long",
        side="long",
        qty=qty,
        entry_price=100,
        stop=65,
        take_profit=190,
        initial_stop=65,
        opened_at=opened,
        sleeve=sleeve,
        exchange=json.dumps({"list": 7, "stop": 3, "target": 2}),
    )


@pytest.fixture
def core(settings):
    settings.portfolio = Portfolio(core_pct=50, core_targets={"BTC": 60, "PAXG": 40})
    return settings


def test_plans_file_cannot_touch_core_lots(settings, market, tmp_path):
    desk = make_desk(settings, market)
    pos = add_position(desk.db)
    path = tmp_path / "actions.json"
    path.write_text(
        json.dumps(
            {
                "market_view": "v",
                "position_actions": [{"position_id": pos, "action": "close", "reason": "x"}],
            }
        )
    )
    [r] = desk.check_plans(path)
    assert r["status"] == "rejected" and r["reasons"] == [CORE_ACTION]
    assert desk.db.one("SELECT status FROM positions")["status"] == "open"


SPOT_POSITION = {
    "id": 1,
    "symbol": "BTCUSDT",
    "asset": "BTC",
    "entry_price": 100.0,
    "qty": 0.5,
    "stop": 94.0,
    "take_profit": 111.0,
    "exchange": json.dumps({"list": 7, "stop": 3, "target": 2}),
}


@respx.mock
def test_spot_close_puts_the_stop_back_when_the_sell_fails(settings):
    respx.get(f"{SPOT}/api/v3/order").mock(
        return_value=httpx.Response(200, json={"status": "NEW", "executedQty": "0"})
    )
    respx.delete(f"{SPOT}/api/v3/orderList").mock(return_value=httpx.Response(200, json={}))
    respx.post(f"{SPOT}/api/v3/order").mock(
        return_value=httpx.Response(400, json={"code": -2010, "msg": "rejected"})
    )
    oco = respx.post(f"{SPOT}/api/v3/orderList/oco").mock(
        return_value=httpx.Response(200, json=OCO)
    )
    broker = SpotBroker(settings, Client(SPOT, "k", "s"), FakeMarket())
    with pytest.raises(CloseFailed) as err:
        broker.close(SPOT_POSITION)
    assert err.value.refs == {"list": 9, "target": 2, "stop": 3}
    sent = params(oco.calls[0])
    assert sent["quantity"] == "0.5" and sent["belowStopPrice"] == "94"


@respx.mock
def test_spot_close_without_full_stop_sells_only_what_is_free(settings):
    respx.get(f"{SPOT}/api/v3/order").mock(
        return_value=httpx.Response(200, json={"status": "PARTIALLY_FILLED", "executedQty": "0.3"})
    )
    respx.get(f"{SPOT}/api/v3/account").mock(
        return_value=httpx.Response(
            200, json={"balances": [{"asset": "BTC", "free": "0.2", "locked": "0"}]}
        )
    )
    respx.delete(f"{SPOT}/api/v3/orderList").mock(return_value=httpx.Response(200, json={}))
    sell = respx.post(f"{SPOT}/api/v3/order").mock(
        return_value=httpx.Response(
            200, json={"executedQty": "0.2", "cummulativeQuoteQty": "22", "status": "FILLED"}
        )
    )
    broker = SpotBroker(settings, Client(SPOT, "k", "s"), FakeMarket())
    exit_ = broker.close(SPOT_POSITION)
    assert params(sell.calls[0])["quantity"] == "0.2"
    assert exit_.pnl == pytest.approx(10 * 0.2 - (110 + 100) * 0.2 * 0.001)


@respx.mock
def test_spot_exit_pnl_counts_fees(settings):
    respx.get(f"{SPOT}/api/v3/order").mock(
        return_value=httpx.Response(
            200, json={"status": "FILLED", "executedQty": "0.5", "cummulativeQuoteQty": "55.5"}
        )
    )
    broker = SpotBroker(settings, Client(SPOT, "k", "s"), FakeMarket())
    exit_ = broker.exit_status(SPOT_POSITION)
    assert exit_.pnl == pytest.approx(11 * 0.5 - (111 + 100) * 0.5 * 0.001)


class FailingClose(PaperBroker):
    def close(self, position):
        raise CloseFailed("sell rejected", {"list": 99, "stop": 98, "target": 97})


def test_failed_trim_leaves_the_lot_protected(core, market):
    desk = make_desk(core, market)
    desk._broker = FailingClose(core, market, desk.db)
    pos = add_position(desk.db, qty=5)
    trim = desk.db.insert(
        "trims",
        position_id=pos,
        asset="BTC",
        qty=5,
        price=100,
        value=500,
        reason="r",
        status="approved",
        created_at=now(),
        updated_at=now(),
    )
    [line] = desk.execute(trim=trim)
    assert "failed" in line
    row = desk.db.one("SELECT * FROM positions WHERE id = ?", pos)
    assert row["status"] == "open" and json.loads(row["exchange"])["stop"] == 98
    assert desk.db.one("SELECT status FROM trims")["status"] == "failed"


def test_approved_plan_is_checked_again_before_placing(settings, db, market, tmp_path):
    desk = make_desk(settings, market)
    [r] = desk.check_plans(plans_file(tmp_path))
    desk.approve(r["id"])
    add_position(
        desk.db, sleeve="active", qty=1, opened=(datetime.now(UTC) - timedelta(hours=1)).isoformat()
    )
    desk.db.conn.execute(
        "UPDATE positions SET status = 'closed', pnl = -100, closed_at = ?", (now(),)
    )
    desk.db.conn.commit()
    [line] = desk.execute()
    assert "rejected by the risk check" in line
    plan = desk.db.one("SELECT * FROM plans WHERE id = ?", r["id"])
    assert plan["status"] == "rejected" and "daily loss" in plan["reasons"]


def test_core_buy_is_checked_again_and_respects_the_daily_loss(core, market):
    desk = make_desk(core, market)
    [plan, _] = desk.rebalance(propose=True)["plans"]
    desk.approve(plan["id"])
    add_position(desk.db, asset="ETH", sleeve="active")
    desk.db.conn.execute(
        "UPDATE positions SET status = 'closed', pnl = -100, closed_at = ? WHERE asset = 'ETH'",
        (now(),),
    )
    desk.db.conn.commit()
    desk.execute(only=plan["id"])
    row = desk.db.one("SELECT * FROM plans WHERE id = ?", plan["id"])
    assert row["status"] == "rejected" and "daily loss" in row["reasons"]
    again = desk.rebalance(propose=True)["plans"]
    assert all("daily loss" in " ".join(p["reasons"]) for p in again)


def test_old_proposals_cannot_be_approved_and_expire_on_sync(settings, market, tmp_path):
    desk = make_desk(settings, market)
    [a] = desk.check_plans(plans_file(tmp_path))
    [b] = desk.check_plans(plans_file(tmp_path, horizon="short"))
    old = (datetime.now(UTC) - timedelta(hours=30)).isoformat()
    desk.db.conn.execute("UPDATE plans SET created_at = ?", (old,))
    desk.db.conn.commit()
    with pytest.raises(ValueError, match="older than 24h"):
        desk.approve(a["id"])
    assert f"plan {b['id']} expired unapproved" in desk.sync()
    assert {p["status"] for p in desk.db.all("SELECT status FROM plans")} == {"expired"}


@respx.mock
def test_spot_equity_counts_coins_of_pending_plans(settings, db):
    respx.get(f"{SPOT}/api/v3/account").mock(
        return_value=httpx.Response(
            200,
            json={
                "balances": [
                    {"asset": "USDT", "free": "100", "locked": "0"},
                    {"asset": "DOGE", "free": "10", "locked": "0"},
                ]
            },
        )
    )
    db.insert(
        "plans",
        asset="DOGE",
        symbol="DOGEUSDT",
        horizon="mid",
        side="long",
        rating="buy",
        entry_type="limit",
        entry=1,
        stop=0.9,
        take_profit=1.2,
        confidence=70,
        thesis="t",
        invalidation="i",
        status="placed",
        created_at=now(),
        updated_at=now(),
    )
    broker = SpotBroker(settings, Client(SPOT, "k", "s"), FakeMarket(2.0), db)
    assert broker.equity() == 120


def test_loss_limits_are_capped():
    with pytest.raises(ValidationError):
        RiskLimits(daily_loss_limit_pct=30)
    with pytest.raises(ValidationError):
        RiskLimits(max_drawdown_pct=60)


def test_leaving_a_profile_keeps_keys_from_the_file(tmp_path, monkeypatch):
    cfg = tmp_path / "desk.toml"
    cfg.write_text('[risk]\nprofile = "aggressive"\nprincipal = 500.0\nfloor_pct = 50.0\n')
    monkeypatch.setenv("DESK_CONFIG", str(cfg))
    new = settings_io.update({"risk": {"profile": None, "risk_per_trade_pct": 2.0}})
    assert new.risk.floor_pct == 50 and new.risk.principal == 500
    assert tomllib.loads(cfg.read_text())["risk"]["floor_pct"] == 50


def test_trims_of_removed_assets_wait_even_with_auto_execute(core, market):
    core.execution.auto_execute = True
    market.prices["ETHUSDT"] = 10
    desk = make_desk(core, market)
    add_position(desk.db, asset="ETH", qty=1)
    [t] = desk.rebalance(propose=True)["trims"]
    assert desk.db.one("SELECT status FROM trims WHERE id = ?", t["id"])["status"] == "proposed"


def test_futures_skips_the_core(core, market):
    core.market = Market.FUTURES
    desk = make_desk(core, market)
    r = desk.rebalance(propose=True)
    assert r["plans"] == [] and r["trims"] == []
    assert desk.db.one("SELECT COUNT(*) AS n FROM plans")["n"] == 0
    assert desk.book().sleeve_equity is None


def test_core_targets_cannot_be_cash():
    with pytest.raises(ValidationError):
        Portfolio(core_pct=30, core_targets={"BTC": 50, "USDC": 50})
    with pytest.raises(ValidationError):
        Settings(quote="BTC", portfolio=Portfolio(core_pct=30, core_targets={"BTC": 100}))


def test_lots_with_an_approved_trim_are_left_out(core, market):
    desk = make_desk(core, market)
    lot = add_position(desk.db, qty=1)
    desk.db.insert(
        "trims",
        position_id=lot,
        asset="BTC",
        qty=1,
        price=100,
        value=100,
        reason="r",
        status="approved",
        created_at=now(),
        updated_at=now(),
    )
    assert portfolio.holdings(desk.db) == []
    btc = {r["asset"]: r for r in portfolio.current(desk, 1000)}["BTC"]
    assert btc["value"] == 0


def test_execute_only_sends_the_approved_item(core, market):
    desk = make_desk(core, market)
    lot = add_position(desk.db, qty=1)
    trim = desk.db.insert(
        "trims",
        position_id=lot,
        asset="BTC",
        qty=1,
        price=100,
        value=100,
        reason="r",
        status="approved",
        created_at=now(),
        updated_at=now(),
    )
    plans = desk.rebalance(propose=True)["plans"]
    for p in plans:
        desk.approve(p["id"])
    out = desk.execute(only=plans[0]["id"])
    assert out == [f"plan {plans[0]['id']}: filled at 100.0"]
    assert desk.db.one("SELECT status FROM trims WHERE id = ?", trim)["status"] == "approved"
    assert desk.db.one("SELECT status FROM plans WHERE id = ?", plans[1]["id"])["status"] == (
        "approved"
    )
    assert desk.execute(trim=trim) == [f"trim {trim}: sold position {lot}"]


def test_free_cash_counts_approved_market_plans_once(settings, market, tmp_path):
    desk = make_desk(settings, market)
    [r] = desk.check_plans(plans_file(tmp_path, entry_type="market", entry=100, take_profit=113))
    desk.approve(r["id"])
    plan = desk.db.one("SELECT * FROM plans WHERE id = ?", r["id"])
    assert desk.book().free_quote == pytest.approx(1000 - plan["qty"] * plan["entry"])
    assert desk.book(exclude=r["id"]).free_quote == pytest.approx(1000)


def test_allowed_assets_come_from_the_database(settings, market):
    settings.universe.enabled = True
    desk = make_desk(settings, market)
    desk.write_universe()
    path = desk.run_dir(desk.run_id()) / "universe.json"
    path.write_text(json.dumps([{"asset": "SCAM", "source": "scan"}]))
    assert "SCAM" not in desk.book().allowed
    assert "BTC" in {a["asset"] for a in desk.run_assets()}


def test_allocation_adds_up_to_equity(core, market):
    desk = make_desk(core, market)
    add_position(desk.db, qty=2)
    market.prices["BTCUSDT"] = 150
    data = portfolio.state(desk, {"rate": None})
    total = sum(a["value"] for a in data["allocation"]["by_asset"])
    assert total == pytest.approx(data["equity"])


def test_headline_trade_stats_are_active_only():
    base = {
        "side": "long",
        "horizon": "long",
        "entry_price": 100,
        "initial_stop": 90,
        "qty": 1,
        "exit_reason": "manual",
        "opened_at": "2026-10-01T00:00:00+00:00",
        "closed_at": "2026-10-02T00:00:00+00:00",
        "asset": "BTC",
    }
    rows = [base | {"sleeve": "active", "pnl": 10}, base | {"sleeve": "core", "pnl": -50}]
    t = analytics.trade_metrics(rows)
    assert t["sleeve"] == "active" and t["count"] == 1 and t["expectancy_r"] == 1
    assert t["by"]["sleeve"]["core"]["count"] == 1
    assert analytics.trade_metrics(rows, sleeve=None)["count"] == 2
