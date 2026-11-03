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
