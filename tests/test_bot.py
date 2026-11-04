import json

import httpx
import pytest
import respx

from tradedesk.bot import CONFIRM_SECONDS, Bot
from tradedesk.broker.paper import PaperBroker
from tradedesk.desk import Desk
from tradedesk.notify import Telegram

from .test_paper_flow import plans_file

BOT = "https://api.telegram.org/botT"
NOW = 1_800_000_000


def ok(result) -> httpx.Response:
    return httpx.Response(200, json={"ok": True, "result": result})


class Api:
    def __init__(self, mock):
        self.send = mock.post(f"{BOT}/sendMessage").mock(return_value=ok({"message_id": 1}))
        self.edit = mock.post(f"{BOT}/editMessageText").mock(return_value=ok(True))
        self.answer = mock.post(f"{BOT}/answerCallbackQuery").mock(return_value=ok(True))
        self.updates = mock.post(f"{BOT}/getUpdates").mock(return_value=ok([]))

    @staticmethod
    def bodies(route) -> list[dict]:
        return [json.loads(c.request.content) for c in route.calls]


@pytest.fixture
def api():
    with respx.mock(assert_all_called=False) as mock:
        yield Api(mock)


@pytest.fixture
def bot(settings, db, market, tmp_path):
    desk = Desk(settings, db, PaperBroker(settings, market, db))
    desk.start_run()
    (desk.run_dir(desk.run_id()) / "facts.json").write_text(json.dumps({"BTC": {"atr_1d": 3}}))
    return Bot(
        desk,
        Telegram("T", "42", httpx.Client()),
        tmp_path / "data" / "telegram_offset",
        sleep=lambda s: None,
        clock=lambda: NOW,
    )


def message(text: str, chat: int = 42, uid: int = 1, kind: str = "private") -> dict:
    return {"update_id": uid, "message": {"chat": {"id": chat, "type": kind}, "text": text}}


def press(data: str, chat: int = 42, uid: int = 1, kind: str = "private", sender: int = 42) -> dict:
    return {
        "update_id": uid,
        "callback_query": {
            "id": "cb",
            "data": data,
            "from": {"id": sender},
            "message": {"message_id": 55, "chat": {"id": chat, "type": kind}},
        },
    }


def proposed(bot, tmp_path, **kw) -> int:
    [r] = bot.desk.check_plans(plans_file(tmp_path, **kw))
    return r["id"]


def test_approve_runs_approve_then_execute(bot, api, tmp_path):
    plan_id = proposed(bot, tmp_path, entry_type="market", entry=100, take_profit=113)
    bot.handle(press(f"approve:{plan_id}"))
    assert bot.desk.db.one("SELECT status FROM plans")["status"] == "open"
    [edit] = Api.bodies(api.edit)
    assert edit["message_id"] == 55
    assert "<b>Approved</b>, plan 1: filled at 100" in edit["text"]
    assert Api.bodies(api.answer)[0]["text"] == "Approved"


def test_approve_twice_does_nothing(bot, api, tmp_path):
    plan_id = proposed(bot, tmp_path)
    bot.handle(press(f"approve:{plan_id}"))
    bot.handle(press(f"approve:{plan_id}"))
    assert bot.desk.db.one("SELECT status FROM plans")["status"] == "placed"
    assert "Already placed, nothing done." in Api.bodies(api.edit)[1]["text"]


def test_drop_rejects_only_waiting_plans(bot, api, tmp_path):
    plan_id = proposed(bot, tmp_path)
    bot.handle(press(f"drop:{plan_id}"))
    assert bot.desk.db.one("SELECT status FROM plans")["status"] == "cancelled"
    assert Api.bodies(api.edit)[0]["text"].endswith("<b>Dropped</b>")
    bot.handle(press(f"drop:{plan_id}"))
    assert "Already cancelled" in Api.bodies(api.edit)[1]["text"]


def test_other_chats_are_ignored(bot, api, tmp_path):
    plan_id = proposed(bot, tmp_path)
    bot.handle(press(f"approve:{plan_id}", chat=666))
    bot.handle(message("/kill", chat=666))
    bot.handle({"update_id": 3, "edited_message": {"chat": {"id": 42}, "text": "/status"}})
    assert bot.desk.db.one("SELECT status FROM plans")["status"] == "proposed"
    assert not api.send.called and not api.edit.called and not api.answer.called


def test_groups_and_other_senders_are_ignored(bot, api, tmp_path):
    plan_id = proposed(bot, tmp_path)
    bot.handle(press(f"approve:{plan_id}", kind="group"))
    bot.handle(press(f"approve:{plan_id}", sender=7))
    bot.handle(message("/status", kind="supergroup"))
    assert bot.desk.db.one("SELECT status FROM plans")["status"] == "proposed"
    assert not api.send.called and not api.edit.called


def test_approve_sends_only_that_plan(bot, api, tmp_path):
    first = proposed(bot, tmp_path)
    bot.desk.approve(first)
    second = proposed(bot, tmp_path, horizon="short", entry_type="market", take_profit=113)
    bot.handle(press(f"approve:{second}"))
    statuses = dict((r["id"], r["status"]) for r in bot.desk.db.all("SELECT * FROM plans"))
    assert statuses == {first: "approved", second: "open"}


def test_kill_asks_then_cancels_without_flatten(bot, api, tmp_path):
    proposed(bot, tmp_path, entry_type="market", entry=100, take_profit=113)
    bot.desk.approve(1)
    bot.desk.execute()
    proposed(bot, tmp_path, asset="ETH")
    bot.handle(message("/kill"))
    [ask] = Api.bodies(api.send)
    buttons = ask["reply_markup"]["inline_keyboard"][0]
    assert buttons[0]["callback_data"] == f"kill:{NOW}"
    assert bot.desk.db.one("SELECT status FROM plans WHERE id = 2")["status"] == "proposed"
    bot.handle(press(buttons[0]["callback_data"]))
    assert bot.desk.db.one("SELECT status FROM plans WHERE id = 2")["status"] == "cancelled"
    assert len(bot.desk.db.open_positions()) == 1
    assert "plan 2 cancelled" in Api.bodies(api.edit)[0]["text"]


def test_flatten_confirm_closes_positions(bot, api, tmp_path):
    proposed(bot, tmp_path, entry_type="market", entry=100, take_profit=113)
    bot.desk.approve(1)
    bot.desk.execute()
    bot.handle(message("/flatten"))
    data = Api.bodies(api.send)[0]["reply_markup"]["inline_keyboard"][0][0]["callback_data"]
    assert data == f"flatten:{NOW}"
    bot.handle(press(data))
    assert bot.desk.db.open_positions() == []
    assert "position 1 closed" in Api.bodies(api.edit)[0]["text"]


def test_keep_and_stale_confirm_do_nothing(bot, api, tmp_path):
    proposed(bot, tmp_path, entry_type="market", entry=100, take_profit=113)
    bot.desk.approve(1)
    bot.desk.execute()
    bot.handle(press("keep:0"))
    bot.handle(press(f"flatten:{NOW - CONFIRM_SECONDS - 1}"))
    assert len(bot.desk.db.open_positions()) == 1
    assert "expired" in Api.bodies(api.edit)[1]["text"]


def test_commands(bot, api, tmp_path):
    proposed(bot, tmp_path)
    bot.handle(message("/plans"))
    bot.handle(message("/status@deskbot"))
    bot.handle(message("/report"))
    bot.handle(message("hello"))
    plans, status, report, help_ = Api.bodies(api.send)
    assert plans["reply_markup"]["inline_keyboard"][0][0]["callback_data"] == "approve:1"
    assert "equity 1000.00 USDT" in status["text"] and "Open positions:" in status["text"]
    assert report["text"].startswith("<b>Desk report")
    assert "/flatten" in help_["text"]


def test_offset_is_kept(bot, api):
    api.updates.mock(return_value=ok([message("/help", uid=10), message("/help", uid=11)]))
    assert bot.poll() == 2
    assert bot.offset_path.read_text() == "12"
    again = Bot(bot.desk, bot.telegram, bot.offset_path)
    api.updates.mock(return_value=ok([]))
    again.poll()
    assert json.loads(api.updates.calls[-1].request.content)["offset"] == 12
    assert json.loads(api.updates.calls[-1].request.content)["timeout"] == 50


def test_a_bad_update_still_moves_the_offset(bot, api, capsys):
    api.updates.mock(return_value=ok([press("approve:999", uid=5)]))
    api.edit.mock(return_value=httpx.Response(400, json={"ok": False, "description": "nope"}))
    bot.poll()
    assert bot.offset_path.read_text() == "6"
    assert "update 5 failed" in capsys.readouterr().err


def test_network_errors_back_off(bot, api, capsys):
    waits: list[float] = []
    bot.sleep = waits.append
    api.updates.mock(side_effect=[httpx.ConnectError("down")] * 7 + [ok([])])
    polls = iter(range(9))
    bot.run(stop=lambda: next(polls) >= 8)
    assert waits == [2, 4, 8, 16, 32, 60, 60]
    assert "retrying in 2s" in capsys.readouterr().err


def test_approve_says_when_a_plan_expired(bot, api, tmp_path):
    plan_id = proposed(bot, tmp_path)
    bot.desk.db.update("plans", plan_id, created_at="2020-01-01T00:00:00+00:00")
    bot.handle(press(f"approve:{plan_id}"))
    assert bot.desk.db.one("SELECT status FROM plans")["status"] == "expired"
    assert "Expired before it was approved" in Api.bodies(api.edit)[0]["text"]
