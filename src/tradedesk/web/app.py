from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from markdown_it import MarkdownIt

from tradedesk.desk import Desk

HERE = Path(__file__).parent
md = MarkdownIt("commonmark", {"html": False, "linkify": False}).enable("table")


def guard(x_desk: str | None) -> None:
    if x_desk != "1":
        raise HTTPException(403, "missing X-Desk header")


def create_app(desk: Desk) -> FastAPI:
    app = FastAPI(title="tradedesk", docs_url=None, redoc_url=None)
    app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
    db = desk.db

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return (HERE / "templates" / "index.html").read_text()

    @app.get("/api/runs")
    def runs() -> list[dict]:
        return db.all("SELECT * FROM runs ORDER BY started_at DESC LIMIT 30")

    @app.get("/api/runs/{run_id}/events")
    def events(run_id: str, after: int = 0) -> list[dict]:
        rows = db.events(run_id, after)
        for r in rows:
            r["html"] = md.render(r["body"]) if r["body"] else ""
        return rows

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
