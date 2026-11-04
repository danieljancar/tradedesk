import math
import statistics
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from tradedesk import analytics
from tradedesk.broker.paper import PaperBroker
from tradedesk.config import Portfolio
from tradedesk.desk import Desk
from tradedesk.indicators import Candle
from tradedesk.web.app import create_app

EQUITY = [
    ("2026-10-01T08:00:00+00:00", 90),
    ("2026-10-01T20:00:00+00:00", 100),
    ("2026-10-02T20:00:00+00:00", 110),
    ("2026-10-03T20:00:00+00:00", 99),
    ("2026-10-04T20:00:00+00:00", 104.5),
]


def position(asset, side, horizon, entry, stop, qty, pnl, reason, hours):
    return {
        "asset": asset,
        "side": side,
        "horizon": horizon,
        "sleeve": "active",
        "entry_price": entry,
        "initial_stop": stop,
        "qty": qty,
        "pnl": pnl,
        "exit_reason": reason,
        "opened_at": "2026-10-01T00:00:00+00:00",
        "closed_at": f"2026-10-0{1 + hours // 24}T{hours % 24:02d}:00:00+00:00",
    }


TRADES = [
    position("BTC", "long", "mid", 100, 90, 1, 20, "target", 24),
    position("ETH", "long", "short", 50, 45, 2, -10, "stop", 12),
    position("BTC", "short", "mid", 100, 110, 1, 5, "manual", 36),
]


def rows(points):
    return [{"ts": ts, "value": v} for ts, v in points]


def test_equity_metrics_by_hand():
    m = analytics.equity_metrics(rows(EQUITY))
    assert m["days"] == 4 and m["start_equity"] == 100
    assert m["total_return_pct"] == 4.5
    assert m["max_drawdown_pct"] == -10.0
    assert m["current_drawdown_pct"] == -5.0
    assert [r["pct"] for r in m["daily_returns"]] == [10.0, -10.0, 5.556]
    assert m["best_day"] == {"d": "2026-10-02", "pct": 10.0}
    assert m["worst_day"] == {"d": "2026-10-03", "pct": -10.0}
    assert m["sharpe"] is None and m["sortino"] is None


def test_sharpe_and_sortino_after_fourteen_days():
    values, v = [], 100.0
    for i in range(15):
        values.append((f"2026-10-{i + 1:02d}T12:00:00+00:00", v))
        v *= 1.02 if i % 2 == 0 else 0.99
    m = analytics.equity_metrics(rows(values))
    rets = [values[i][1] / values[i - 1][1] - 1 for i in range(1, 15)]
    mean = statistics.mean(rets)
    assert m["sharpe"] == round(mean / statistics.stdev(rets) * math.sqrt(365), 2)
    down = math.sqrt(sum(min(r, 0) ** 2 for r in rets) / len(rets))
    assert m["sortino"] == round(mean / down * math.sqrt(365), 2)


def test_trade_metrics_by_hand():
    t = analytics.trade_metrics(TRADES)
    assert t["count"] == 3 and t["win_rate"] == 0.667
    assert t["profit_factor"] == 2.5
    assert t["expectancy_r"] == 0.5 and t["expectancy_quote"] == 5
    assert t["avg_win_r"] == 1.25 and t["avg_loss_r"] == -1
    assert t["avg_hold_hours"] == 24
    assert t["by"]["asset"]["BTC"] == {"count": 2, "pnl": 25, "win_rate": 1.0, "avg_r": 1.25}
    assert t["by"]["exit_reason"]["stop"]["avg_r"] == -1
    assert set(t["by"]) == {"asset", "horizon", "side", "sleeve", "exit_reason"}


def candle(day, close):
    t = int(datetime(2026, 10, day, tzinfo=UTC).timestamp() * 1000)
    return Candle(t, close, close, close, close, 1.0)


def test_benchmark_is_btc_bought_with_the_first_equity():
    points = analytics.daily(rows(EQUITY))
    out = analytics.benchmark(
        points, [candle(d, c) for d, c in ((1, 50), (2, 55), (3, 60), (4, 40))]
    )
    assert [x["value"] for x in out] == [100, 110, 120, 80]
    assert [x["d"] for x in out] == [d for d, _ in points]


def test_fx_rate():
    assert analytics.fx_rate("USDT", "CHF", lambda s: ("2026-11-02", 0.8))["rate"] == 0.8
    gone = analytics.fx_rate("USDT", "CHF", lambda s: None)
    assert gone["rate"] is None and "did not answer" in gone["note"]
    assert analytics.fx_rate("USDT", "USD")["rate"] == 1.0
    assert analytics.fx_rate("USDT", "EUR")["rate"] is None


@pytest.fixture
def api(settings, db, market, monkeypatch):
    monkeypatch.setattr("tradedesk.web.app.market_data", lambda *a, **k: market)
    monkeypatch.setattr(analytics, "_fred_last", lambda s: ("2026-11-02", 0.8))
    settings.portfolio = Portfolio(core_pct=50, core_targets={"BTC": 60, "PAXG": 40})
    desk = Desk(settings, db, PaperBroker(settings, market, db))
    desk.start_run()
    for ts, v in EQUITY:
        db.conn.execute("INSERT INTO equity (ts, value) VALUES (?, ?)", (ts, v))
    db.conn.commit()
    market.candles = [candle(d, c) for d, c in ((1, 50), (2, 55), (3, 60), (4, 40))]
    return TestClient(create_app(desk)), desk


def test_analytics_route(api):
    c, _ = api
    data = c.get("/api/analytics").json()
    assert data["metrics"]["total_return_pct"] == 4.5
    assert data["metrics"]["end_equity_base"] == round(104.5 * 0.8, 2)
    assert data["equity"][2] == {"d": "2026-10-03", "value": 99, "drawdown_pct": -10.0}
    assert [x["value"] for x in data["benchmark"]] == [100, 110, 120, 80]
    assert data["trades"]["count"] == 0


def test_portfolio_route(api):
    c, desk = api
    desk.rebalance(propose=True)
    data = c.get("/api/portfolio").json()
    assert data["equity"] == 1000 and data["equity_base"] == 800
    assert data["sleeves"]["core"]["value"] == 0 and data["sleeves"]["active"]["share"] == 100
    assert [r["asset"] for r in data["core"]] == ["BTC", "PAXG"]
    assert data["core"][0]["target"] == 300
    assert len(data["pending"]["plans"]) == 2
    assert data["allocation"]["by_class"] == [{"class": "cash", "value": 1000, "share": 100}]
    for p in data["pending"]["plans"]:
        desk.approve(p["id"])
    desk.execute()
    data = c.get("/api/portfolio").json()
    assert data["sleeves"]["core"]["share"] == 50
    classes = {x["class"]: x["share"] for x in data["allocation"]["by_class"]}
    assert classes == {"cash": 50, "bitcoin": 30, "gold": 20}
    assert all(r["action"] == "hold" for r in data["core"])
