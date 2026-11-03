import json
import time
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from markdown_it import MarkdownIt

from tradedesk import wire
from tradedesk.binance import market_data
from tradedesk.desk import Desk
from tradedesk.replay import replay

HERE = Path(__file__).parent
DIST = HERE / "dist"
TIMEFRAMES = {"1h", "4h", "1d", "1w"}
NOT_BUILT = """<!doctype html><meta charset="utf-8"><title>tradedesk · Trading floor</title>
<p>The dashboard isn't built. Run <code>cd frontend && pnpm install && pnpm build</code>.</p>"""
md = MarkdownIt("commonmark", {"html": False, "linkify": False}).enable("table")


def guard(x_desk: str | None) -> None:
    if x_desk != "1":
        raise HTTPException(403, "missing X-Desk header")


def create_app(desk: Desk) -> FastAPI:
    app = FastAPI(title="tradedesk", docs_url=None, redoc_url=None)
    if (DIST / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")
    db = desk.db
    cache: dict[tuple, tuple[float, list]] = {}

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        page = DIST / "index.html"
        return page.read_text() if page.exists() else NOT_BUILT

    @app.get("/api/candles/{asset}")
    def candles(asset: str, tf: str = "1d", limit: int = 200) -> list[dict]:
        asset = asset.upper()
        if asset not in desk.settings.watchlist or tf not in TIMEFRAMES:
            raise HTTPException(404, "unknown asset or timeframe")
        key = (asset, tf, limit)
        hit = cache.get(key)
        if hit and time.monotonic() - hit[0] < 60:
            return hit[1]
        try:
            rows = market_data(desk.settings).klines(
                desk.settings.symbol(asset), tf, max(10, min(limit, 500))
            )
        except Exception as e:
            raise HTTPException(502, f"Binance did not answer: {e}") from e
        out = [
            {
                "time": c.open_time // 1000,
                "open": c.open,
                "high": c.high,
                "low": c.low,
                "close": c.close,
                "volume": c.volume,
            }
            for c in rows
        ]
        cache[key] = (time.monotonic(), out)
        return out

    @app.get("/api/runs")
    def runs() -> list[dict]:
        return db.all("SELECT * FROM runs ORDER BY started_at DESC LIMIT 30")

    @app.get("/api/runs/{run_id}/events")
    def events(run_id: str, after: int = 0) -> list[dict]:
        rows = db.events(run_id, after)
        for r in rows:
            r["html"] = md.render(r["body"]) if r["body"] else ""
        return rows

    @app.get("/api/runs/{run_id}/facts")
    def facts(run_id: str) -> dict:
        if run_id not in {r["id"] for r in db.all("SELECT id FROM runs")}:
            raise HTTPException(404, "unknown run")
        path = desk.run_dir(run_id) / "facts.json"
        return json.loads(path.read_text()) if path.exists() else {}

    @app.get("/api/news")
    def headlines() -> list[dict]:
        return wire.headlines()[:150]

    @app.get("/api/report")
    def report() -> dict:
        """Everything since this database started: runs, every idea replayed on real 1h candles."""
        settings = desk.settings
        runs = db.all("SELECT id, started_at, status, summary FROM runs ORDER BY started_at")
        calls = {
            r["run_id"]: r["title"]
            for r in db.all(
                "SELECT run_id, title FROM events"
                " WHERE actor = 'pm' AND kind != 'start' ORDER BY id"
            )
        }
        for r in runs:
            r["call"] = calls.get(r["id"])
        plans = db.all("SELECT * FROM plans ORDER BY created_at")
        equity = db.all("SELECT ts, value FROM equity ORDER BY ts")
        start_eq = equity[0]["value"] if equity else settings.paper_equity
        hour = 3_600_000
        candles: dict[str, list] = {}
        for p in plans:
            sym = p["symbol"]
            if sym not in candles:
                first = min(q["created_at"] for q in plans if q["symbol"] == sym)
                start_ms = int(datetime.fromisoformat(first).timestamp() * 1000) - hour
                try:
                    candles[sym] = market_data(settings).klines(sym, "1h", 1000, start_ms)
                except Exception:
                    candles[sym] = []
            out = replay(p, candles[sym], settings.execution.entry_ttl_hours)
            risk = p["risk_amount"] or start_eq * settings.risk.risk_per_trade_pct / 100
            p["replay"] = out | {"pnl": round(out["r"] * risk, 2)}
        closed = db.all("SELECT * FROM positions WHERE status = 'closed' ORDER BY closed_at")
        return {
            "since": runs[0]["started_at"] if runs else None,
            "start_equity": start_eq,
            "equity": equity,
            "runs": runs,
            "plans": plans,
            "closed": closed,
            "realized": round(sum(p["pnl"] or 0 for p in closed), 2),
        }

    @app.get("/api/state")
    def state() -> dict:
        positions = db.open_positions()
        for p in positions:
            try:
                p["price"] = desk.broker.price(p["symbol"])
            except Exception:
                p["price"] = None
        return {
            "mode": desk.settings.mode,
            "market": desk.settings.market,
            "quote": desk.settings.quote,
            "limits": desk.settings.risk.model_dump(),
            "auto_execute": desk.settings.execution.auto_execute,
            "equity": db.all("SELECT ts, value FROM equity ORDER BY ts DESC LIMIT 200")[::-1],
            "positions": positions,
            "plans": db.all(
                "SELECT * FROM plans WHERE status IN ('proposed', 'approved', 'placed', 'rejected')"
                " AND created_at >= datetime('now', '-3 days') ORDER BY id DESC LIMIT 30"
            ),
            "closed": db.all(
                "SELECT * FROM positions WHERE status = 'closed' ORDER BY closed_at DESC LIMIT 15"
            ),
        }

    @app.post("/api/plans/{plan_id}/approve")
    def approve(plan_id: int, x_desk: str | None = Header(None)) -> dict:
        guard(x_desk)
        try:
            desk.approve(plan_id)
        except ValueError as e:
            raise HTTPException(409, str(e)) from e
        return {"result": desk.execute()}

    @app.post("/api/plans/{plan_id}/reject")
    def reject(plan_id: int, x_desk: str | None = Header(None)) -> dict:
        guard(x_desk)
        desk.reject(plan_id)
        return {"result": "dropped"}

    @app.post("/api/positions/{position_id}/close")
    def close(position_id: int, x_desk: str | None = Header(None)) -> dict:
        guard(x_desk)
        try:
            desk.close(position_id, "closed from dashboard")
        except ValueError as e:
            raise HTTPException(409, str(e)) from e
        return {"result": "closed"}

    @app.post("/api/sync")
    def sync(x_desk: str | None = Header(None)) -> dict:
        guard(x_desk)
        return {"result": desk.sync()}

    return app
