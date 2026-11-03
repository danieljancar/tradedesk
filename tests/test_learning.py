import json
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from tradedesk import learning
from tradedesk.broker.paper import PaperBroker
from tradedesk.desk import Desk
from tradedesk.indicators import Candle
from tradedesk.web.app import create_app

H = 3_600_000
T0 = datetime.now(UTC).replace(minute=0, second=0, microsecond=0) - timedelta(days=5)
START = int(T0.timestamp() * 1000)


def bars(market, *rows):
    """(open, high, low, close) per hour from T0."""
    market.candles = [
        Candle(START + i * H, o, h, lo, c, 1.0) for i, (o, h, lo, c) in enumerate(rows)
    ]


def add_plan(db, run_id="r1", status="proposed", confidence=70, side="long", **kw):
    row = dict(
        run_id=run_id,
        asset="BTC",
        symbol="BTCUSDT",
        horizon="short",
        side=side,
        rating="buy",
        entry_type="limit",
        entry=100.0,
        stop=95.0 if side == "long" else 105.0,
        take_profit=110.0 if side == "long" else 90.0,
        confidence=confidence,
        thesis="t",
        invalidation="i",
        status=status,
        reasons="",
        created_at=T0.isoformat(),
        updated_at=T0.isoformat(),
    )
    return db.insert("plans", **(row | kw))


def make_desk(settings, db, market):
    return Desk(settings, db, PaperBroker(settings, market, db))


def test_learn_records_outcomes_with_context(settings, db, market):
    desk = make_desk(settings, db, market)
    db.insert("runs", id="r1", started_at=T0.isoformat(), status="done")
    facts = {
        "_market": {"fear_greed": [{"value": 22, "label": "Fear"}], "dominance": {"BTC": 57.0}},
        "BTC": {"price": 101, "frames": {"1d": {"rsi": 41.0, "ema200": 90}}, "change": {"7d": -3}},
    }
    learning.store_snapshot(db, "r1", facts, T0.isoformat())
    win = add_plan(db, status="closed")
    loss = add_plan(db, status="rejected", side="short")
    waiting = add_plan(db, entry=50.0, stop=45.0)
    bars(market, (101, 102, 99, 100), (100, 111, 100, 110), *[(110, 110, 110, 110)] * 30)
    assert desk.learn()["ideas"] == 3

    out = {r["plan_id"]: r for r in db.all("SELECT * FROM outcomes")}
    assert out[win]["outcome"] == "target" and out[win]["r"] == 2.0
    assert out[win]["decision"] == "taken" and out[win]["resolved_at"]
    assert out[loss]["outcome"] == "stop" and out[loss]["decision"] == "rejected"
    assert out[waiting]["outcome"] == "expired"
    assert out[win]["fear_greed"] == 22 and out[win]["above_ema200_1d"] == 1
    assert out[win]["btc_dominance"] == 57.0 and out[win]["change_7d"] == -3

    # Resolved ideas are not replayed again.
    assert desk.learn()["ideas"] == 0


def test_open_idea_updates_then_times_out(settings, db, market):
    settings.hold_days.short = 30
    desk = make_desk(settings, db, market)
    pid = add_plan(db)
    bars(market, (100, 101, 99, 100), (100, 103, 99, 102))
    desk.learn()
    row = db.one("SELECT * FROM outcomes WHERE plan_id = ?", pid)
    assert row["outcome"] == "open" and row["resolved_at"] is None and row["r"] == 0.4
    settings.hold_days.short = 1
    desk.learn()
    assert db.one("SELECT outcome FROM outcomes WHERE plan_id = ?", pid)["outcome"] == "timeout"


def test_sync_skips_recently_checked_ideas(settings, db, market):
    settings.hold_days.short = 30
    add_plan(db)
    bars(market, (100, 101, 99, 100))
    assert learning.learn(db, settings, market)["ideas"] == 1
    assert learning.learn(db, settings, market, timedelta(hours=1))["ideas"] == 0
    assert learning.learn(db, settings, market)["ideas"] == 1


def test_after_run_moves(settings, db, market):
    db.insert("runs", id="r1", started_at=T0.isoformat(), status="done")
    learning.store_snapshot(db, "r1", {"BTC": {"price": 100.0}}, T0.isoformat())
    rows = [(100, 100, 100, 100)] * 24 + [(104, 104, 104, 104)] * 48 + [(97, 97, 97, 97)] * 5
    bars(market, *rows)
    assert learning.learn(db, settings, market)["moves"] == 1
    snap = db.one("SELECT * FROM snapshots")
    assert snap["move_24h"] == 4.0 and snap["move_72h"] == -3.0


def test_backfill_reads_facts_json(settings, db):
    db.insert("runs", id="old", started_at=T0.isoformat(), status="done")
    folder = settings.runs_dir / "old"
    folder.mkdir(parents=True)
    (folder / "facts.json").write_text(json.dumps({"_market": {}, "ETH": {"price": 3000}}))
    assert learning.backfill_snapshots(db, settings) == 1
    assert learning.backfill_snapshots(db, settings) == 0


def outcome(db, r, confidence=70, decision="taken", side="long"):
    pid = add_plan(db, confidence=confidence, side=side)
    db.insert(
        "outcomes",
        plan_id=pid,
        run_id="r1",
        asset="BTC",
        side=side,
        horizon="mid",
        confidence=confidence,
        decision=decision,
        outcome="target" if r > 0 else "stop",
        r=r,
        updated_at=T0.isoformat(),
    )


def test_stats_math(db):
    for i in range(10):
        outcome(db, 2.0 if i < 4 else -1.0, confidence=80)
    for _ in range(3):
        outcome(db, -1.0, confidence=60, decision="rejected", side="short")
    s = learning.stats(db)
    assert s["overall"] == {"n": 13, "hit_rate": 0.308, "avg_r": -0.08, "enough": True}
    assert s["by_confidence"]["75+"] == {"n": 10, "hit_rate": 0.4, "avg_r": 0.2, "enough": True}
    assert s["by_confidence"]["55-64"]["n"] == 3
    assert s["by_decision"]["rejected"]["avg_r"] == -1.0
    assert s["by_side"]["short"]["enough"] is False


def test_pass_days_and_bull_bear(db):
    for i, move in enumerate([2.0, -1.0, 3.0]):
        db.insert("runs", id=f"p{i}", started_at=T0.isoformat(), status="done")
        db.insert(
            "snapshots", run_id=f"p{i}", asset="BTC", ts=T0.isoformat(), facts="{}", move_24h=move
        )
        db.log(f"p{i}", "bull", "output", "case")
        db.log(f"p{i}", "bear", "output", "case")
    add_plan(db, run_id="p2")
    s = learning.stats(db)
    assert s["pass_days"]["runs"] == 2
    assert s["pass_days"]["24h"] == {
        "n": 2,
        "avg_pct": 0.5,
        "avg_abs_pct": 1.5,
        "up_share": 0.5,
        "enough": False,
    }
    assert s["bull_bear"]["24h"]["bull"] == 2 and s["bull_bear"]["24h"]["bear"] == 1
    assert s["bull_bear"]["72h"]["n"] == 0


def test_min_sample_guardrail(settings, db, market):
    for _ in range(9):
        outcome(db, 1.0)
    text = learning.report(learning.stats(db))
    assert "overall: not enough data yet (n 9)" in text
    assert "hit" not in text.split("overall:")[1].splitlines()[0]
    assert learning.summary_line(learning.stats(db)) is None
    desk = make_desk(settings, db, market)
    desk.start_run()
    assert "calibration" not in desk.write_book().read_text()

    outcome(db, -1.0)
    line = learning.summary_line(learning.stats(db))
    assert line == "calibration: hit 90%, avg +0.80R (n 10); 65-74 hit 90%, avg +0.80R (n 10)"
    assert line in desk.write_book().read_text()


def test_learning_endpoint(settings, db, market):
    outcome(db, 2.0)
    body = TestClient(create_app(make_desk(settings, db, market))).get("/api/learning").json()
    assert body["overall"]["n"] == 1 and body["min_sample"] == 10
    assert set(body["pass_days"]) == {"runs", "24h", "72h"}
