import json
from datetime import UTC, datetime, timedelta

import pytest

from tradedesk import gate
from tradedesk.broker.paper import PaperBroker
from tradedesk.config import Gate
from tradedesk.desk import Desk


@pytest.fixture
def desk(settings, db, market, monkeypatch):
    settings.gate = Gate(enabled=True, move_atr=1, max_gap_hours=4, headlines=2)
    d = Desk(settings, db, PaperBroker(settings, market, db))
    run_id = d.start_run()
    d.finish_run("ok")
    (d.run_dir(run_id) / "facts.json").write_text(json.dumps({"BTC": {"price": 100, "atr_4h": 2}}))
    monkeypatch.setattr(gate.wire, "headlines", lambda: [])
    return d


def test_quiet_market_skips(desk, market):
    market.default = 101
    assert gate.reasons(desk) == []


def test_a_real_move_runs(desk, market):
    market.default = 103
    assert "BTC moved 1.5" in gate.reasons(desk)[0]


def test_long_gap_runs(desk, market):
    market.default = 100
    later = datetime.now(UTC) + timedelta(hours=5)
    assert any("last run" in r for r in gate.reasons(desk, later))


def test_market_moving_news_runs(desk, market, monkeypatch):
    market.default = 100
    ts = datetime.now(UTC).timestamp() + 60
    news = [{"ts": ts, "title": "Fed signals rate cut"}, {"ts": ts, "title": "SEC approves ETF"}]
    monkeypatch.setattr(gate.wire, "headlines", lambda: news)
    assert any("headlines" in r for r in gate.reasons(desk))
