import json
from datetime import datetime

import httpx
import pytest
import respx

from tradedesk import notify
from tradedesk.broker.paper import PaperBroker
from tradedesk.config import Notify
from tradedesk.desk import Desk

from .test_paper_flow import plans_file

BOT = "https://api.telegram.org/botT"


def sent(route) -> list[dict]:
    return [json.loads(c.request.content) for c in route.calls]


@pytest.fixture
def tg():
    with respx.mock(assert_all_called=False) as mock:
        route = mock.post(f"{BOT}/sendMessage").mock(
            return_value=httpx.Response(200, json={"ok": True, "result": {"message_id": 7}})
        )
        yield route


def make(settings, db, market, hour=12, **cfg):
    settings.notify = Notify(telegram=True, **cfg)
    desk = Desk(settings, db, PaperBroker(settings, market, db))
    desk.start_run()
    (desk.run_dir(desk.run_id()) / "facts.json").write_text(json.dumps({"BTC": {"atr_1d": 3}}))
    telegram = notify.Telegram("T", "42", httpx.Client())
    desk.listeners.append(notify.Notifier(desk, telegram, clock=lambda: datetime(2026, 1, 1, hour)))
    return desk


def test_proposed_plan_asks_for_approval(settings, db, market, tmp_path, tg):
    desk = make(settings, db, market)
    [r] = desk.check_plans(plans_file(tmp_path, thesis="breakout <above> 100 & holds"))
    [msg] = sent(tg)
    assert msg["chat_id"] == "42" and msg["parse_mode"] == "HTML"
    text = msg["text"]
    assert "<b>BTC long mid</b>" in text
    assert "entry 99 (limit), stop 94, target 111" in text
    assert "size 2 (198.00 USDT), risk 10.00, R/R 2.4" in text
    assert "breakout &lt;above&gt; 100 &amp; holds" in text
    buttons = msg["reply_markup"]["inline_keyboard"][0]
    assert [b["callback_data"] for b in buttons] == [f"approve:{r['id']}", f"drop:{r['id']}"]


def test_auto_execute_only_informs(settings, db, market, tmp_path, tg):
    settings.execution.auto_execute = True
    desk = make(settings, db, market)
    desk.check_plans(plans_file(tmp_path))
    [msg] = sent(tg)
    assert "reply_markup" not in msg
    assert "auto_execute is on" in msg["text"]


def test_fill_exit_run_and_kill(settings, db, market, tmp_path, tg):
    desk = make(settings, db, market)
    [r] = desk.check_plans(plans_file(tmp_path, entry_type="market", entry=100, take_profit=113))
    desk.approve(r["id"])
    desk.execute()
    market.add(low=93, high=99)
    desk.sync()
    desk.finish_run("Bought BTC, stopped out.")
    desk.kill(flatten=False)
    texts = [m["text"] for m in sent(tg)]
    assert any("filled</b>" in t and "stop 94 on the exchange" in t for t in texts)
    exit_ = next(t for t in texts if "closed</b>" in t)
    assert "by stop" in exit_ and "pnl -" in exit_ and "R)" in exit_
    assert any(t.startswith("<b>Run ") and "stopped out" in t for t in texts)
    assert any(t.startswith("<b>Kill switch</b>") for t in texts)


def test_events_filter(settings, db, market, tmp_path, tg):
    desk = make(settings, db, market, events=["run"])
    desk.check_plans(plans_file(tmp_path))
    desk.finish_run("done")
    assert [m["text"][:8] for m in sent(tg)] == ["<b>Run 2"]


def test_quiet_hours_let_only_errors_and_stops_through(settings, db, market, tmp_path, tg):
    desk = make(settings, db, market, hour=2, quiet_hours="23-07")
    [r] = desk.check_plans(plans_file(tmp_path, entry_type="market", entry=100, take_profit=113))
    desk.approve(r["id"])
    desk.execute()
    desk.log("exchange", "error", "Order for plan 9 failed", "timeout")
    market.add(low=93, high=99)
    desk.sync()
    desk.finish_run("quiet")
    texts = [m["text"] for m in sent(tg)]
    assert len(texts) == 2
    assert texts[0].startswith("<b>Exchange error</b>")
    assert "by stop" in texts[1]


def test_no_stop_alert_always_goes_out(settings, db, market, tg):
    desk = make(settings, db, market, hour=3, quiet_hours="22-08", events=["run"])
    desk.log("exchange", "error", "No working stop on BTC", "stop order <missing>")
    [msg] = sent(tg)
    assert msg["text"].startswith("<b>NO WORKING STOP</b>")
    assert "&lt;missing&gt;" in msg["text"]


def test_quiet_window():
    q = Notify(quiet_hours="23-07")
    assert q.quiet(23) and q.quiet(0) and q.quiet(6)
    assert not q.quiet(7) and not q.quiet(22)
    day = Notify(quiet_hours="12-14")
    assert day.quiet(13) and not day.quiet(14)
    assert not Notify().quiet(3)
    with pytest.raises(ValueError):
        Notify(quiet_hours="late")
    with pytest.raises(ValueError):
        Notify(quiet_hours="23-25")


def test_classify():
    def ev(actor, kind, title="x"):
        return {"actor": actor, "kind": kind, "title": title}

    assert notify.classify(ev("risk", "pass")) == "proposed"
    assert notify.classify(ev("risk", "reject")) is None
    assert notify.classify(ev("exchange", "fill")) == "fill"
    assert notify.classify(ev("exchange", "exit")) == "exit"
    assert notify.classify(ev("exchange", "error")) == "error"
    assert notify.classify(ev("exchange", "order")) is None
    assert notify.classify(ev("desk", "done")) == "run"
    assert notify.classify(ev("desk", "kill")) == "kill"
    assert notify.classify(ev("desk", "error")) is None
    assert notify.no_stop(ev("exchange", "error", "No working stop on BTC"))


def test_send_failure_never_breaks_trading(settings, db, market, tmp_path, capsys):
    with respx.mock:
        respx.post(f"{BOT}/sendMessage").mock(side_effect=httpx.ConnectError("down"))
        desk = make(settings, db, market)
        [r] = desk.check_plans(plans_file(tmp_path))
        assert r["status"] == "proposed"
    with respx.mock:
        respx.post(f"{BOT}/sendMessage").mock(
            return_value=httpx.Response(400, json={"ok": False, "description": "bad html"})
        )
        desk.finish_run("x")
    err = capsys.readouterr().err.strip().splitlines()
    assert err == ["telegram: down", "telegram: sendMessage: bad html"]
    assert db.one("SELECT status FROM runs")["status"] == "done"


def test_attach_needs_env(settings, db, market, monkeypatch, capsys):
    desk = Desk(settings, db, PaperBroker(settings, market, db))
    assert notify.attach(desk) is None
    settings.notify = Notify(telegram=True)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    assert notify.attach(desk) is None
    assert "TELEGRAM_BOT_TOKEN" in capsys.readouterr().err
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "T")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "42")
    assert notify.attach(desk) in desk.listeners


def test_digest(settings, db, market, tmp_path):
    desk = Desk(settings, db, PaperBroker(settings, market, db))
    desk.start_run()
    (desk.run_dir(desk.run_id()) / "facts.json").write_text(json.dumps({"BTC": {"atr_1d": 3}}))
    db.insert("equity", ts="2020-01-01T00:00:00+00:00", value=990.0)
    desk.check_plans(plans_file(tmp_path))
    [r] = desk.check_plans(
        plans_file(tmp_path, asset="ETH", entry_type="market", entry=100, take_profit=113)
    )
    desk.approve(r["id"])
    desk.execute()
    desk.finish_run("Long ETH. " + "word " * 400)
    text = notify.digest(desk)
    assert "equity 1000.00 USDT (+10.00 in 24h), realized today +0.00" in text
    assert "1 open:" in text and "ETH long mid" in text and "open +0.00" in text
    assert "1 plans waiting for approval:" in text and "plan 1 BTC long mid" in text
    assert "Long ETH." in text and text.endswith("...")
    assert len(text) <= 1200
    html = notify.digest(desk, html=True)
    assert html.startswith("<b>Desk report")
    assert len(html) <= 1250
