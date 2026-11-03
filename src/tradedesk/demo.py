"""Replays a made-up run so the trading floor can be seen without keys or market access."""

import threading
import time
from datetime import UTC, datetime, timedelta

from tradedesk.db import Database, now
from tradedesk.desk import Desk

STEPS = [
    ("desk", "start", "Run demo started (paper spot)", None, []),
    ("prices", "start", "Pulling candles, funding and open interest", None, []),
    ("headlines", "start", "Reading news feeds", None, []),
    (
        "book",
        "output",
        "Equity 1000.00, 0 open",
        "# Book\nequity 1000.00 | flat | no lessons yet",
        [],
    ),
    (
        "prices",
        "output",
        "Snapshot for BTC, ETH, SOL",
        "## BTCUSDT price 100,000 | 7d +2.1%\n4h: rsi 58 | 1d: rsi 61 | sample numbers",
        [],
    ),
    (
        "headlines",
        "output",
        "41 headlines sorted by asset",
        "## BTC\n- [3h, demo] Sample headline",
        [],
    ),
    ("technical", "start", "technical is working", None, ["prices", "book"]),
    ("news", "start", "news is working", None, ["headlines"]),
    (
        "technical",
        "output",
        "BTC has the cleanest trend, SOL the weakest chart",
        "## BTC\nUp on 1d and 1w, range on 4h. Support 97,000, resistance 104,000.\n\n"
        "## SOL\nBelow ema50 on 1d, funding positive while price falls.",
        ["prices", "book"],
    ),
    (
        "news",
        "output",
        "CPI on Thursday is the event that matters this week",
        "## Macro\nCPI Thursday, FOMC minutes Wednesday.\n\n## BTC\nNothing material.",
        ["headlines"],
    ),
    ("bull", "start", "bull is working", None, ["technical", "news", "book"]),
    ("bear", "start", "bear is working", None, ["technical", "news", "book"]),
    (
        "bull",
        "output",
        "BTC mid-term long from the 97,000 retest",
        "Entry 97,500, stop 94,800 under the 1d swing low, target 104,000 at resistance.",
        ["technical", "news", "book"],
    ),
    (
        "bear",
        "output",
        "Don't add size into CPI, SOL longs are crowded",
        "Funding on SOL is positive while price falls. CPI Thursday can flush late longs.",
        ["technical", "news", "book"],
    ),
    ("pm", "start", "pm is working", None, ["technical", "news", "bull", "bear", "book"]),
    (
        "pm",
        "output",
        "One trade: BTC mid-term long at 97,500, half confidence until CPI",
        "## Market view\nTrend intact, event risk Thursday.\n\n## Ideas\n- BTC long mid, entry "
        "97,500, stop 94,800, target 104,000, confidence 64",
        ["technical", "news", "bull", "bear", "book"],
    ),
    ("risk", "start", "Checking 2 ideas against the rules", None, []),
    ("risk", "reject", "Rejected: SOL long short", "reward/risk 1.40 below 2.0", []),
    ("risk", "pass", "Passed: BTC long mid, 0.0037 at 97500, risk 10.00, R/R 2.41", None, []),
    ("desk", "done", "Run finished", "1 plan waiting for approval", []),
]


def replay(desk: Desk, run_id: str, pause: float) -> None:
    for actor, kind, title, body, refs in STEPS:
        desk.db.log(run_id, actor, kind, title, body, refs)
        time.sleep(pause)
    desk.db.update("runs", run_id, finished_at=now(), status="done")


def prepare(desk: Desk) -> str:
    run_id = datetime.now(UTC).strftime("demo-%H%M%S")
    desk.db.insert("runs", id=run_id, started_at=now())
    start = datetime.now(UTC) - timedelta(days=30)
    for i in range(31):
        value = 1000 + i * 2.5 + (8 if i % 4 == 0 else -5)
        ts = (start + timedelta(days=i)).isoformat(timespec="seconds")
        desk.db.conn.execute("INSERT OR REPLACE INTO equity VALUES (?, ?)", (ts, value))
    desk.db.conn.commit()
    desk.db.insert(
        "plans",
        run_id=run_id,
        asset="BTC",
        symbol="BTCUSDT",
        horizon="mid",
        side="long",
        rating="buy",
        entry_type="limit",
        entry=97500,
        stop=94800,
        take_profit=104000,
        confidence=64,
        thesis="Sample plan from the demo run. Trend up on 1d and 1w, retest of 97,000 support.",
        invalidation="daily close under 94,800",
        status="proposed",
        reasons="",
        qty=0.0037,
        risk_amount=10,
        reward_risk=2.41,
        leverage=1,
        created_at=now(),
        updated_at=now(),
    )
    return run_id


def start(desk: Desk, pause: float = 1.6) -> None:
    run_id = prepare(desk)
    threading.Thread(target=replay, args=(desk, run_id, pause), daemon=True).start()


def demo_db(path) -> Database:
    if path.exists():
        path.unlink()
    return Database(path)
