import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL DEFAULT 'running',
    summary TEXT
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY,
    run_id TEXT,
    ts TEXT NOT NULL,
    actor TEXT NOT NULL,
    kind TEXT NOT NULL,
    title TEXT NOT NULL,
    body TEXT,
    refs TEXT
);
CREATE TABLE IF NOT EXISTS plans (
    id INTEGER PRIMARY KEY,
    run_id TEXT,
    asset TEXT NOT NULL,
    symbol TEXT NOT NULL,
    horizon TEXT NOT NULL,
    side TEXT NOT NULL,
    rating TEXT NOT NULL,
    entry_type TEXT NOT NULL,
    entry REAL NOT NULL,
    stop REAL NOT NULL,
    take_profit REAL NOT NULL,
    confidence INTEGER NOT NULL,
    thesis TEXT NOT NULL,
    invalidation TEXT NOT NULL,
    status TEXT NOT NULL,
    reasons TEXT,
    qty REAL,
    risk_amount REAL,
    reward_risk REAL,
    leverage INTEGER,
    exchange TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS positions (
    id INTEGER PRIMARY KEY,
    plan_id INTEGER REFERENCES plans(id),
    symbol TEXT NOT NULL,
    asset TEXT NOT NULL,
    horizon TEXT NOT NULL,
    side TEXT NOT NULL,
    qty REAL NOT NULL,
    entry_price REAL NOT NULL,
    stop REAL NOT NULL,
    take_profit REAL NOT NULL,
    initial_stop REAL NOT NULL,
    opened_at TEXT NOT NULL,
    closed_at TEXT,
    exit_price REAL,
    pnl REAL,
    exit_reason TEXT,
    status TEXT NOT NULL DEFAULT 'open',
    exchange TEXT
);
CREATE TABLE IF NOT EXISTS equity (
    ts TEXT PRIMARY KEY,
    value REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS snapshots (
    run_id TEXT NOT NULL,
    asset TEXT NOT NULL,
    ts TEXT NOT NULL,
    price REAL,
    facts TEXT NOT NULL,
    market TEXT,
    move_24h REAL,
    move_72h REAL,
    PRIMARY KEY (run_id, asset)
);
CREATE TABLE IF NOT EXISTS outcomes (
    plan_id INTEGER PRIMARY KEY REFERENCES plans(id),
    run_id TEXT,
    asset TEXT NOT NULL,
    side TEXT NOT NULL,
    horizon TEXT NOT NULL,
    confidence INTEGER NOT NULL,
    decision TEXT NOT NULL,
    outcome TEXT NOT NULL,
    r REAL NOT NULL,
    filled_at TEXT,
    resolved_at TEXT,
    updated_at TEXT NOT NULL,
    fear_greed INTEGER,
    btc_dominance REAL,
    funding_pct REAL,
    rsi_1d REAL,
    atr_pct_1d REAL,
    vol_ratio_1d REAL,
    change_7d REAL,
    above_ema200_1d INTEGER
);
CREATE TABLE IF NOT EXISTS trims (
    id INTEGER PRIMARY KEY,
    run_id TEXT,
    position_id INTEGER NOT NULL REFERENCES positions(id),
    asset TEXT NOT NULL,
    qty REAL NOT NULL,
    price REAL NOT NULL,
    value REAL NOT NULL,
    reason TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS run_universe (
    run_id TEXT PRIMARY KEY,
    assets TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS flows (
    id INTEGER PRIMARY KEY,
    ts TEXT NOT NULL,
    amount REAL NOT NULL,
    kind TEXT NOT NULL,
    note TEXT
);
CREATE INDEX IF NOT EXISTS events_run ON events(run_id, id);
CREATE INDEX IF NOT EXISTS plans_status ON plans(status);
CREATE INDEX IF NOT EXISTS positions_status ON positions(status);
"""
# (table, column, definition) added to databases created before the column existed
COLUMNS = [
    ("outcomes", "source", "TEXT"),
    ("outcomes", "asset_class", "TEXT"),
    ("plans", "sleeve", "TEXT NOT NULL DEFAULT 'active'"),
    ("positions", "sleeve", "TEXT NOT NULL DEFAULT 'active'"),
]


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class Database:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript(SCHEMA)
        self.migrate()

    def migrate(self) -> None:
        for table, column, definition in COLUMNS:
            have = {r["name"] for r in self.conn.execute(f"PRAGMA table_info({table})")}
            if column not in have:
                with self.tx() as c:
                    c.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    @contextmanager
    def tx(self) -> Iterator[sqlite3.Connection]:
        with self.conn:
            yield self.conn

    def all(self, sql: str, *args: Any) -> list[dict]:
        return [dict(r) for r in self.conn.execute(sql, args).fetchall()]

    def one(self, sql: str, *args: Any) -> dict | None:
        row = self.conn.execute(sql, args).fetchone()
        return dict(row) if row else None

    def insert(self, table: str, **values: Any) -> int:
        cols = ", ".join(values)
        marks = ", ".join("?" for _ in values)
        with self.tx() as c:
            cur = c.execute(
                f"INSERT INTO {table} ({cols}) VALUES ({marks})", tuple(values.values())
            )
            return cur.lastrowid or 0

    def upsert(self, table: str, keys: tuple[str, ...], **values: Any) -> None:
        cols = ", ".join(values)
        marks = ", ".join("?" for _ in values)
        sets = ", ".join(f"{k} = excluded.{k}" for k in values if k not in keys)
        with self.tx() as c:
            c.execute(
                f"INSERT INTO {table} ({cols}) VALUES ({marks}) "
                f"ON CONFLICT ({', '.join(keys)}) DO UPDATE SET {sets}",
                tuple(values.values()),
            )

    def update(self, table: str, row_id: int | str, **values: Any) -> None:
        sets = ", ".join(f"{k} = ?" for k in values)
        with self.tx() as c:
            c.execute(f"UPDATE {table} SET {sets} WHERE id = ?", (*values.values(), row_id))

    def latest_run(self) -> dict | None:
        return self.one("SELECT * FROM runs ORDER BY started_at DESC LIMIT 1")

    def log(
        self,
        run_id: str | None,
        actor: str,
        kind: str,
        title: str,
        body: str | None = None,
        refs: list[str] | None = None,
    ) -> int:
        return self.insert(
            "events",
            run_id=run_id,
            ts=now(),
            actor=actor,
            kind=kind,
            title=title,
            body=body,
            refs=json.dumps(refs or []),
        )

    def events(self, run_id: str, after: int = 0) -> list[dict]:
        rows = self.all(
            "SELECT * FROM events WHERE run_id = ? AND id > ? ORDER BY id", run_id, after
        )
        for r in rows:
            r["refs"] = json.loads(r["refs"] or "[]")
        return rows

    def open_positions(self) -> list[dict]:
        return self.all("SELECT * FROM positions WHERE status = 'open' ORDER BY opened_at")

    def pending_plans(self) -> list[dict]:
        return self.all(
            "SELECT * FROM plans WHERE status IN ('approved', 'placed') ORDER BY created_at"
        )

    def record_equity(self, value: float, ts: str | None = None) -> None:
        with self.tx() as c:
            c.execute(
                "INSERT OR REPLACE INTO equity (ts, value) VALUES (?, ?)", (ts or now(), value)
            )

    def peak_equity(self) -> float | None:
        """Highest equity, with money moved in or out since then counted as if it was there."""
        row = self.one(
            "SELECT MAX(e.value - COALESCE((SELECT SUM(f.amount) FROM flows f "
            "WHERE f.ts <= e.ts), 0)) AS v FROM equity e"
        )
        if not row or row["v"] is None:
            return None
        return row["v"] + self.net_flows()

    def net_flows(self) -> float:
        row = self.one("SELECT COALESCE(SUM(amount), 0) AS v FROM flows")
        return row["v"] if row else 0.0

    def record_flow(self, amount: float, kind: str, note: str = "", ts: str | None = None) -> None:
        with self.tx() as c:
            c.execute(
                "INSERT INTO flows (ts, amount, kind, note) VALUES (?, ?, ?, ?)",
                (ts or now(), amount, kind, note),
            )

    def realized_since(self, iso_ts: str) -> float:
        row = self.one(
            "SELECT COALESCE(SUM(pnl), 0) AS v FROM positions WHERE status = 'closed' "
            "AND closed_at >= ?",
            iso_ts,
        )
        return row["v"] if row else 0.0

    def save_universe(self, run_id: str, assets: list[dict]) -> None:
        self.upsert(
            "run_universe", ("run_id",), run_id=run_id, assets=json.dumps(assets), created_at=now()
        )

    def run_universe(self, run_id: str) -> list[dict] | None:
        row = self.one("SELECT assets FROM run_universe WHERE run_id = ?", run_id)
        return json.loads(row["assets"]) if row else None
