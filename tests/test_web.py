from fastapi.testclient import TestClient

from tradedesk.broker.paper import PaperBroker
from tradedesk.desk import Desk
from tradedesk.web.app import create_app


def client(settings, db, market):
    desk = Desk(settings, db, PaperBroker(settings, market, db))
    run_id = desk.start_run()
    db.log(run_id, "bull", "output", "BTC long", "## BTC\n<script>x</script> **case**")
    return TestClient(create_app(desk)), run_id


def test_events_render_markdown_without_raw_html(settings, db, market):
    c, run_id = client(settings, db, market)
    events = c.get(f"/api/runs/{run_id}/events").json()
    bull = events[-1]
    assert "<strong>case</strong>" in bull["html"]
    assert "<script>" not in bull["html"]


def test_actions_need_the_desk_header(settings, db, market):
    c, _ = client(settings, db, market)
    assert c.post("/api/sync").status_code == 403
    assert c.post("/api/sync", headers={"X-Desk": "1"}).status_code == 200


def test_page_and_state_load(settings, db, market):
    c, _ = client(settings, db, market)
    assert "Trading floor" in c.get("/").text
    assert c.get("/api/candles/DOGE").status_code == 404
    state = c.get("/api/state").json()
    assert state["mode"] == "paper"
    assert state["invested"] == 1000
    assert state["positions"] == []


def test_notes_reach_the_book(settings, db, market):
    c, _ = client(settings, db, market)
    h = {"X-Desk": "1"}
    assert c.post("/api/notes", json={"text": "watch 75k"}).status_code == 403
    n = c.post(
        "/api/notes",
        json={"kind": "level", "asset": "btc", "price": 75000, "text": "big support"},
        headers=h,
    ).json()
    assert n["asset"] == "BTC" and n["price"] == 75000
    assert [x["id"] for x in c.get("/api/notes").json()] == [n["id"]]
    from tradedesk import notes

    assert any("big support" in line for line in notes.book_lines(db))
    c.delete(f"/api/notes/{n['id']}", headers=h)
    assert c.get("/api/notes").json() == []


def test_settings_edit_validates_and_protects_mode(settings, db, market, tmp_path, monkeypatch):
    cfg = tmp_path / "desk.toml"
    cfg.write_text('mode = "paper"\n[risk]\nrisk_per_trade_pct = 1.0\n')
    monkeypatch.setenv("DESK_CONFIG", str(cfg))
    c, _ = client(settings, db, market)
    h = {"X-Desk": "1"}
    assert c.put("/api/settings", json={"mode": "live"}, headers=h).status_code == 422
    assert (
        c.put("/api/settings", json={"risk": {"risk_per_trade_pct": 99}}, headers=h).status_code
        == 422
    )
    r = c.put(
        "/api/settings",
        json={"risk": {"risk_per_trade_pct": 2.5}, "watchlist": ["eth", "sol"]},
        headers=h,
    )
    assert r.status_code == 200
    assert r.json()["settings"]["risk"]["risk_per_trade_pct"] == 2.5
    assert 'mode = "paper"' in cfg.read_text() and settings.watchlist == ["ETH", "SOL"]


def test_index_candles_and_patterns(settings, db, market, monkeypatch):
    days = [(f"2024-{1 + i // 28:02d}-{1 + i % 28:02d}", 5000 + (i % 20) * 10) for i in range(300)]
    monkeypatch.setattr("tradedesk.macro.fred", lambda sid, days_back: days)
    c, _ = client(settings, db, market)
    daily = c.get("/api/candles/SPX?tf=1d&limit=100").json()
    assert len(daily) == 100 and daily[-1]["close"] == days[-1][1]
    weekly = c.get("/api/candles/SPX?tf=1w&limit=500").json()
    assert len(weekly) < len(days)
    assert c.get("/api/candles/SPX?tf=4h").status_code == 404
    shape = c.get("/api/patterns/SPX").json()
    assert shape["short"] is None
    assert set(shape) == {"short", "mid", "long", "levels"}


def test_index_pages_back_and_monthly(settings, db, market, monkeypatch):
    from tradedesk import macro

    macro._cache.clear()
    # 25 trading days a month, ten years
    day = lambda i: f"20{10 + i // 300}-{1 + (i // 25) % 12:02d}-{1 + i % 25:02d}"  # noqa: E731
    days = [(day(i), 100 + i) for i in range(3000)]
    monkeypatch.setattr("tradedesk.macro.fred", lambda sid, days_back: days)
    c, _ = client(settings, db, market)
    last = c.get("/api/candles/NDX?tf=1d&limit=50").json()
    older = c.get(f"/api/candles/NDX?tf=1d&limit=50&end={last[0]['time'] * 1000 - 1}").json()
    assert older[-1]["time"] < last[0]["time"] and len(older) == 50
    months = c.get("/api/candles/NDX?tf=1M&limit=1000").json()
    assert 100 < len(months) < 200


def test_database_survives_parallel_requests(db):
    from concurrent.futures import ThreadPoolExecutor

    def work(i):
        db.record_flow(1.0, "deposit")
        return db.all("SELECT * FROM flows") and db.one("SELECT COUNT(*) AS n FROM flows")

    with ThreadPoolExecutor(16) as pool:
        assert all(pool.map(work, range(400)))
    assert db.one("SELECT COUNT(*) AS n FROM flows")["n"] == 400


def test_report_starts_at_the_money_put_in(settings, db, market):
    db.record_equity(0.0, ts="2026-11-05T20:00:00+00:00")
    db.record_equity(1050.0, ts="2026-11-05T21:00:00+00:00")
    c, _ = client(settings, db, market)
    rep = c.get("/api/report").json()
    assert rep["start_equity"] == 1000
    assert rep["equity"][0]["value"] == 1050
