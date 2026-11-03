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
    state = c.get("/api/state").json()
    assert state["mode"] == "paper"
    assert state["positions"] == []
