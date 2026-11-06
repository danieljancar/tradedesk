import json
import os
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any

from fastapi import Body, FastAPI, Header, HTTPException
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from markdown_it import MarkdownIt

from tradedesk import (
    analytics,
    ask,
    heatmap,
    learning,
    macro,
    notes,
    notify,
    patterns,
    portfolio,
    settings_io,
    trending,
    universe,
    wire,
)
from tradedesk.binance import market_data
from tradedesk.config import ROOT
from tradedesk.desk import Desk
from tradedesk.replay import replay

HERE = Path(__file__).parent
DIST = HERE / "dist"
TIMEFRAMES = {"1h", "4h", "1d", "1w", "1M"}
NOT_BUILT = """<!doctype html><meta charset="utf-8"><title>tradedesk · Trading floor</title>
<p>The dashboard isn't built. Run <code>cd frontend && pnpm install && pnpm build</code>.</p>"""
md = MarkdownIt("commonmark", {"html": False, "linkify": False}).enable("table")


def guard(x_desk: str | None) -> None:
    if x_desk != "1":
        raise HTTPException(403, "missing X-Desk header")


class Assets(StaticFiles):
    """Built files carry a content hash in their name, so the browser can keep them for good."""

    def file_response(self, *args, **kwargs):
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response


def create_app(desk: Desk) -> FastAPI:
    app = FastAPI(title="tradedesk", docs_url=None, redoc_url=None)
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    if (DIST / "assets").is_dir():
        app.mount("/assets", Assets(directory=DIST / "assets"), name="assets")
    db = desk.db
    cache: dict[tuple, tuple[float, Any]] = {}

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        page = DIST / "index.html"
        return page.read_text() if page.exists() else NOT_BUILT

    def bars(asset: str, tf: str, limit: int, end: int | None = None) -> list:
        asset = asset.upper()
        index = asset in macro.INDEXES
        known = {*desk.settings.watchlist, "BTC", "ETH", *(a["asset"] for a in desk.run_assets())}
        if (
            tf not in TIMEFRAMES
            or not (index or asset in known)
            or (index and tf not in ("1d", "1w", "1M"))
        ):
            raise HTTPException(404, "unknown asset or timeframe")
        limit = max(10, min(limit, 1000))
        key = (asset, tf, limit, end)
        hit = cache.get(key)
        if hit and time.monotonic() - hit[0] < 60:
            return hit[1]
        try:
            if index:
                rows = macro.index_candles(asset, tf, limit, end)
            else:
                md, symbol = market_data(desk.settings), desk.settings.symbol(asset)
                if end:
                    rows = md.klines(symbol, tf, limit, end_ms=end)
                else:
                    rows = md.klines(symbol, tf, limit)
        except Exception as e:
            source = "FRED" if index else "Binance"
            raise HTTPException(502, f"{source} did not answer: {e}") from e
        cache[key] = (time.monotonic(), rows)
        return rows

    @app.get("/api/candles/{asset}")
    def candles(asset: str, tf: str = "1d", limit: int = 200, end: int | None = None) -> list[dict]:
        """`end` in ms returns the bars up to that time, for loading history on scroll."""
        return [
            {
                "time": c.open_time // 1000,
                "open": c.open,
                "high": c.high,
                "low": c.low,
                "close": c.close,
                "volume": c.volume,
            }
            for c in bars(asset, tf, limit, end)
        ]

    @app.get("/api/patterns/{asset}")
    def chart_patterns(asset: str) -> dict:
        """Trendline patterns at three scales and the long-term levels, for the chart."""
        index = asset.upper() in macro.INDEXES
        out: dict[str, Any] = {}
        for scale, (tf, lookback, width) in patterns.SCALES.items():
            if index and tf == "4h":
                out[scale] = None
                continue
            try:
                rows = bars(asset, tf, lookback)
            except HTTPException:
                out[scale] = None
                continue
            found = patterns.find(rows, lookback=lookback, width=width)
            out[scale] = found and {**found, "tf": tf}
        try:
            out["levels"] = patterns.levels(bars(asset, "1w", 500))
        except HTTPException:
            out["levels"] = []
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

    @app.get("/api/macro")
    def macro_overview() -> dict:
        data = macro.overview()
        if data is None:
            raise HTTPException(502, "macro sources did not answer")
        return data

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

    @app.get("/api/learning")
    def learning_stats() -> dict:
        """Calibration from the outcomes table, read only. `desk learn` or `desk sync` fills it."""
        return learning.stats(db)

    desks = [(desk, "")] + ([(desk.linked, "f")] if desk.linked else [])

    def resolve(ref: str) -> tuple[Desk, int]:
        target, raw = (desk.linked, ref[1:]) if ref.startswith("f") and desk.linked else (desk, ref)
        try:
            return target, int(raw)
        except ValueError as e:
            raise HTTPException(404, "unknown id") from e

    def tagged(sql: str) -> list[dict]:
        rows = []
        for d, prefix in desks:
            for r in d.db.all(sql):
                rows.append({**r, "id": f"{prefix}{r['id']}", "venue": d.settings.market.value})
        return rows

    def equity_series() -> list[dict]:
        rows = db.all("SELECT ts, value FROM equity ORDER BY ts DESC LIMIT 200")[::-1]
        if not desk.linked:
            return rows
        other = desk.linked.db.all("SELECT ts, value FROM equity ORDER BY ts")
        out, i, last = [], 0, 0.0
        for r in rows:
            while i < len(other) and other[i]["ts"] <= r["ts"]:
                last = other[i]["value"]
                i += 1
            out.append({"ts": r["ts"], "value": r["value"] + last})
        return out

    def starting() -> bool:
        """daily.sh holds this lock while it runs, before the agents open the run."""
        cfg = Path(os.environ.get("DESK_CONFIG", "desk.toml")).stem
        return (ROOT / "data" / "logs" / f"{cfg}.lock").is_dir()

    @app.get("/api/state")
    def state() -> dict:
        positions = tagged("SELECT * FROM positions WHERE status = 'open' ORDER BY opened_at")
        for p in positions:
            d = desk.linked if p["venue"] == "futures" and desk.linked else desk
            try:
                p["price"] = d.broker.price(p["symbol"])
            except Exception:
                p["price"] = None
        return {
            "mode": desk.settings.mode,
            "busy": starting(),
            "market": desk.settings.market,
            "venues": [d.settings.market.value for d, _ in desks],
            "peer": desk.settings.peer_dashboard or None,
            "quote": desk.settings.quote,
            "limits": desk.settings.risk.model_dump(),
            "watchlist": desk.settings.watchlist,
            "auto_execute": desk.settings.execution.auto_execute,
            "telegram": {
                "enabled": desk.settings.notify.telegram,
                "configured": notify.from_env() is not None,
            },
            "equity": equity_series(),
            "positions": positions,
            "plans": sorted(
                tagged(
                    "SELECT * FROM plans WHERE status IN "
                    "('proposed', 'approved', 'placed', 'rejected') "
                    "AND created_at >= datetime('now', '-3 days') ORDER BY id DESC LIMIT 30"
                ),
                key=lambda p: p["created_at"],
                reverse=True,
            ),
            "closed": sorted(
                tagged(
                    "SELECT * FROM positions WHERE status = 'closed' "
                    "ORDER BY closed_at DESC LIMIT 15"
                ),
                key=lambda p: p["closed_at"],
                reverse=True,
            )[:15],
        }

    @app.post("/api/plans/{ref}/approve")
    def approve(ref: str, x_desk: str | None = Header(None)) -> dict:
        guard(x_desk)
        target, plan_id = resolve(ref)
        try:
            target.approve(plan_id)
        except ValueError as e:
            raise HTTPException(409, str(e)) from e
        return {"result": target.execute(only=plan_id)}

    @app.post("/api/plans/{ref}/reject")
    def reject(ref: str, x_desk: str | None = Header(None)) -> dict:
        guard(x_desk)
        target, plan_id = resolve(ref)
        target.reject(plan_id)
        return {"result": "dropped"}

    @app.post("/api/positions/{ref}/close")
    def close(ref: str, x_desk: str | None = Header(None)) -> dict:
        guard(x_desk)
        target, position_id = resolve(ref)
        try:
            target.close(position_id, "closed from dashboard")
        except ValueError as e:
            raise HTTPException(409, str(e)) from e
        return {"result": "closed"}

    @app.post("/api/positions/{ref}/stop")
    def move_stop(ref: str, price: float, x_desk: str | None = Header(None)) -> dict:
        guard(x_desk)
        target, position_id = resolve(ref)
        open_row = target.db.one(
            "SELECT id FROM positions WHERE id = ? AND status = 'open'", position_id
        )
        if open_row is None:
            raise HTTPException(404, "no open position with that id")
        result = target.tighten(position_id, price, "moved from dashboard")
        if result["status"] == "rejected":
            raise HTTPException(409, "; ".join(result["reasons"]))
        return result

    @app.get("/api/notes")
    def list_notes() -> list[dict]:
        return notes.active(db)

    @app.post("/api/notes")
    def add_note(body: Annotated[dict, Body()], x_desk: str | None = Header(None)) -> dict:
        guard(x_desk)
        try:
            return notes.add(
                db,
                body.get("kind", "note"),
                body.get("text", ""),
                body.get("asset"),
                body.get("price"),
            )
        except ValueError as e:
            raise HTTPException(422, str(e)) from e

    @app.delete("/api/notes/{note_id}")
    def drop_note(note_id: int, x_desk: str | None = Header(None)) -> dict:
        guard(x_desk)
        notes.archive(db, note_id)
        return {"result": "archived"}

    @app.get("/api/settings")
    def get_settings() -> dict:
        return settings_io.read()

    @app.put("/api/settings")
    def put_settings(body: Annotated[dict, Body()], x_desk: str | None = Header(None)) -> dict:
        guard(x_desk)
        try:
            new = settings_io.update(body)
        except ValueError as e:
            raise HTTPException(422, str(e)) from e
        editable = ("watchlist", "paper_equity", "risk", "execution", "hold_days")
        for field in (*editable, "portfolio", "universe", "notify", "trailing"):
            setattr(desk.settings, field, getattr(new, field))
        return settings_io.read()

    @app.post("/api/run")
    def run_now(x_desk: str | None = Header(None)) -> dict:
        guard(x_desk)
        latest = db.latest_run()
        if starting() or (latest and latest["status"] == "running"):
            raise HTTPException(409, "a run is already going")
        subprocess.Popen(
            ["bash", str(ROOT / "scripts" / "daily.sh")],
            cwd=ROOT,
            env={**os.environ, "FORCE": "1"},
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return {"result": "started"}

    asks = ask.Asks(ROOT, desk.settings.path(desk.settings.db_path).with_suffix(".asks.json"))

    @app.get("/api/ask")
    def ask_list() -> list[dict]:
        return asks.recent()

    @app.post("/api/ask")
    def ask_question(body: Annotated[dict, Body()], x_desk: str | None = Header(None)) -> dict:
        guard(x_desk)
        question = str(body.get("question", "")).strip()
        if not question:
            raise HTTPException(422, "empty question")
        if asks.busy():
            raise HTTPException(409, "still answering the last question")
        run_id = desk.run_id()
        return asks.start(question, desk.run_dir(run_id) if run_id else None)

    @app.post("/api/sync")
    def sync(x_desk: str | None = Header(None)) -> dict:
        guard(x_desk)
        return {"result": desk.sync()}

    @app.get("/api/universe")
    def universe_list(run_id: str | None = None) -> list[dict]:
        run_id = run_id or desk.run_id()
        if not run_id:
            return []
        if run_id not in {r["id"] for r in db.all("SELECT id FROM runs")}:
            raise HTTPException(404, "unknown run")
        return universe.read(desk.run_dir(run_id)) or []

    @app.get("/api/positioning/{asset}")
    def positioning(asset: str, period: str = "4h") -> dict:
        asset = asset.upper()
        known = {*desk.settings.watchlist, "BTC", "ETH", *(a["asset"] for a in desk.run_assets())}
        if asset not in known or period not in {"1h", "4h", "1d"}:
            raise HTTPException(404, "unknown asset or period")
        key = ("positioning", asset, period)
        hit = cache.get(key)
        if hit and time.monotonic() - hit[0] < 300:
            return hit[1]
        out = market_data(desk.settings).positioning(f"{asset}{desk.settings.quote}", period)
        cache[key] = (time.monotonic(), out)
        return out

    @app.get("/api/trending")
    def trending_coins() -> list[dict]:
        hit = cache.get(("listed",))
        if hit and time.monotonic() - hit[0] < 3600:
            listed = hit[1]
        else:
            try:
                symbols = market_data(desk.settings).spot_symbols()
            except Exception:
                symbols = []
            quote = desk.settings.quote
            listed = {
                s["baseAsset"]
                for s in symbols
                if s.get("quoteAsset") == quote and s.get("status") == "TRADING"
            }
            if listed:
                cache[("listed",)] = (time.monotonic(), listed)
        rows = trending.coins(listed)
        if rows is None:
            raise HTTPException(502, "CoinGecko did not answer")
        return rows

    @app.get("/api/heatmap")
    def market_heatmap() -> dict:
        try:
            return heatmap.board()
        except RuntimeError as e:
            raise HTTPException(502, str(e)) from e

    @app.get("/api/analytics")
    def analytics_report() -> dict:
        """Returns, drawdown, ratios, trade stats and BTC buy and hold over the same window."""
        settings = desk.settings
        return analytics.report(db, settings, market_data(settings).klines)

    @app.get("/api/portfolio")
    def portfolio_state() -> dict:
        s = desk.settings
        try:
            return portfolio.state(desk, analytics.fx_rate(s.quote, s.portfolio.base_currency))
        except Exception as e:
            raise HTTPException(502, f"prices did not load: {e}") from e

    @app.post("/api/trims/{trim_id}/approve")
    def approve_trim(trim_id: int, x_desk: str | None = Header(None)) -> dict:
        guard(x_desk)
        try:
            portfolio.approve_trim(desk, trim_id)
        except ValueError as e:
            raise HTTPException(409, str(e)) from e
        return {"result": desk.execute(trim=trim_id)}

    @app.post("/api/trims/{trim_id}/reject")
    def reject_trim(trim_id: int, x_desk: str | None = Header(None)) -> dict:
        guard(x_desk)
        portfolio.reject_trim(desk, trim_id)
        return {"result": "dropped"}

    @app.get("/{path:path}", response_class=HTMLResponse, include_in_schema=False)
    def spa(path: str) -> str:
        # client-side routes (/markets/BTC, /trades, ...) all load the same page
        if path.startswith(("api/", "assets/")):
            raise HTTPException(404, "not found")
        return index()

    return app
