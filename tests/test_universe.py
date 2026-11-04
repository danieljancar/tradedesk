import json

import pytest
from fastapi.testclient import TestClient

from tradedesk import snapshot, universe
from tradedesk.broker.paper import PaperBroker
from tradedesk.config import Universe
from tradedesk.desk import Desk
from tradedesk.indicators import Candle
from tradedesk.web.app import create_app

from .conftest import FakeMarket
from .test_paper_flow import plans_file

DAY = 86_400_000


def ticker(base: str, volume: float, last: float = 10.0, change: float = 1.0) -> dict:
    return {
        "symbol": f"{base}USDT",
        "lastPrice": str(last),
        "priceChangePercent": str(change),
        "quoteVolume": str(volume),
    }


def pair(base: str, quote: str = "USDT", status: str = "TRADING") -> dict:
    return {"symbol": f"{base}{quote}", "baseAsset": base, "quoteAsset": quote, "status": status}


MOVES = {"BTC": 0.003, "MOON": 0.03, "DUMP": -0.03, "FLAT": 0.0, "PAXG": 0.001, "ETH": 0.004}
SWING = {"MOON": 0.06, "DUMP": 0.06}


class ScanMarket(FakeMarket):
    """BTC flat-ish, MOON up hard on a volume spike, DUMP down hard, FLAT and PAXG quiet."""

    def __init__(self):
        super().__init__()
        bases = ["BTC", "ETH", "MOON", "DUMP", "FLAT", "PAXG", "USDC", "FDUSD", "BTCUP", "JUP"]
        self.ticks = [ticker(b, 50_000_000) for b in bases]
        self.ticks[2]["quoteVolume"] = "150000000"
        self.ticks.append(ticker("TINY", 1_000_000))
        self.ticks.append({**ticker("OLD", 90_000_000)})
        self.symbols = [pair(b) for b in [*bases, "TINY"]] + [
            pair("OLD", status="BREAK"),
            pair("ETH", "BTC"),
        ]

    def tickers(self):
        return self.ticks

    def spot_symbols(self):
        return self.symbols

    def klines(self, symbol, interval, limit=200, start_ms=None):
        base = symbol.removesuffix("USDT")
        step, wide = MOVES.get(base, 0.0), SWING.get(base, 0.01)
        out, close = [], 10.0
        for i in range(limit):
            close *= 1 + step
            out.append(Candle(i * DAY, close, close * (1 + wide), close * (1 - wide), close, 1e6))
        return out

    def derivatives(self, symbol):
        return None


@pytest.fixture
def scan_market(monkeypatch) -> ScanMarket:
    m = ScanMarket()
    monkeypatch.setattr("tradedesk.desk.market_data", lambda *a, **k: m)
    monkeypatch.setattr("tradedesk.web.app.market_data", lambda *a, **k: m)
    monkeypatch.setattr(snapshot, "sentiment", lambda: ("fear & greed: not available", {}))
    return m


def test_candidates_filter_stables_leveraged_thin_and_halted(settings):
    m = ScanMarket()
    names = [c["asset"] for c in universe.candidates(settings, m.tickers(), m.spot_symbols())]
    assert names[0] == "MOON"
    assert "JUP" in names
    for gone in ("USDC", "FDUSD", "BTCUP", "TINY", "OLD"):
        assert gone not in names


def test_config_exclude(settings):
    settings.universe = Universe(exclude=["moon"])
    m = ScanMarket()
    names = [c["asset"] for c in universe.candidates(settings, m.tickers(), m.spot_symbols())]
    assert "MOON" not in names


def test_scan_ranks_strong_movers_both_ways(settings):
    settings.universe = Universe(top=3)
    rows = universe.scan(settings, ScanMarket())
    assert {r["asset"] for r in rows[:2]} == {"MOON", "DUMP"}
    assert len(rows) == 3
    moon = next(r for r in rows if r["asset"] == "MOON")
    assert moon["source"] == "scan" and moon["asset_class"] == "crypto"
    assert moon["rel_btc_7d"] > 15 and moon["vol_surge"] > 1
    assert moon["reason"].startswith("up ") and "vs BTC +2%" in moon["reason"]
    dump = next(r for r in rows if r["asset"] == "DUMP")
    assert dump["reason"].startswith("down ") and dump["rel_btc_7d"] < -15
    assert set(universe.FIELDS) <= set(moon)


def test_asset_class():
    assert universe.asset_class("paxg") == "gold"
    assert universe.asset_class("XAUT") == "gold"
    assert universe.asset_class("BTC") == "crypto"


def test_assets_for_run_dedups_and_caps(settings):
    settings.universe = Universe(always=["SOL", "btc"], max_assets=5)
    scanned = [
        universe.entry("ETH", "scan", score=90.0, reason="eth moved"),
        universe.entry("MOON", "scan", score=80.0),
        universe.entry("DUMP", "scan", score=70.0),
    ]
    out = universe.assets_for_run(settings, scanned, extra=["AVAX"])
    assert [(a["asset"], a["source"]) for a in out] == [
        ("BTC", "watchlist"),
        ("ETH", "watchlist"),
        ("SOL", "always"),
        ("PAXG", "gold"),
        ("AVAX", "core"),
    ]
    assert out[1]["reason"] == "eth moved" and out[1]["score"] == 90.0
    assert out[3]["asset_class"] == "gold" and out[0]["price"] is None


def test_no_gold_when_off(settings):
    settings.universe = Universe(include_gold=False)
    assert "PAXG" not in {a["asset"] for a in universe.assets_for_run(settings, [])}


def test_scan_writes_universe_and_snapshot_uses_it(settings, db, scan_market):
    desk = Desk(settings, db, PaperBroker(settings, scan_market, db))
    desk.start_run()
    path = desk.write_universe()
    run_dir = path.parent
    saved = json.loads((run_dir / "universe.json").read_text())
    assert [a["asset"] for a in saved][:3] == ["BTC", "ETH", "PAXG"]
    assert "MOON" in path.read_text() and "volume" in path.read_text()
    assert [a["asset"] for a in desk.run_assets()] == [a["asset"] for a in saved]

    desk.write_snapshot()
    facts = json.loads((run_dir / "facts.json").read_text())
    assert facts["MOON"]["source"] == "scan" and facts["MOON"]["scan_score"] > 0
    assert facts["PAXG"]["asset_class"] == "gold"
    assert "## MOONUSDT" in (run_dir / "snapshot.md").read_text()
    kinds = [(e["actor"], e["kind"]) for e in db.events(desk.run_id())]
    assert ("scanner", "start") in kinds and ("scanner", "output") in kinds


def test_run_assets_falls_back_to_watchlist(settings, db, scan_market):
    desk = Desk(settings, db, PaperBroker(settings, scan_market, db))
    desk.start_run()
    assert [a["asset"] for a in desk.run_assets()] == ["BTC", "ETH"]
    desk.write_universe()
    settings.universe = Universe(enabled=False)
    assert [a["asset"] for a in desk.run_assets()] == ["BTC", "ETH"]


def test_risk_check_uses_the_universe(settings, db, scan_market, tmp_path):
    settings.universe = Universe(top=2)
    desk = Desk(settings, db, PaperBroker(settings, scan_market, db))
    desk.start_run()
    [off] = desk.check_plans(plans_file(tmp_path, asset="MOON"))
    assert any("universe" in r for r in off["reasons"])
    desk.write_universe()
    assert "MOON" in desk.book().allowed
    [on] = desk.check_plans(plans_file(tmp_path, asset="MOON"))
    assert not any("universe" in r for r in on["reasons"])
    [other] = desk.check_plans(plans_file(tmp_path, asset="FLAT"))
    assert "FLAT is not in today's universe" in other["reasons"]


def test_universe_endpoint(settings, db, scan_market):
    desk = Desk(settings, db, PaperBroker(settings, scan_market, db))
    c = TestClient(create_app(desk))
    assert c.get("/api/universe").json() == []
    run_id = desk.start_run()
    desk.write_universe()
    latest = c.get("/api/universe").json()
    assert latest == c.get(f"/api/universe?run_id={run_id}").json()
    assert any(a["source"] == "scan" for a in latest)
    assert c.get("/api/universe?run_id=nope").status_code == 404
    assert c.get("/api/candles/MOON").status_code == 200


def test_learning_keeps_source(settings, db):
    from tradedesk import learning

    ctx = learning.context({"source": "scan", "asset_class": "crypto"}, {})
    assert ctx["source"] == "scan" and ctx["asset_class"] == "crypto"
    assert "by_source" in learning.stats(db)


def test_outcomes_columns_migrate_once(settings):
    from tradedesk.db import Database

    Database(settings.db_path)
    db = Database(settings.db_path)
    cols = {r["name"] for r in db.all("PRAGMA table_info(outcomes)")}
    assert {"source", "asset_class"} <= cols
