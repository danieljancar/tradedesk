"""Long-polling Telegram bot: approve plans, read the book and pull the kill switch from a phone."""

import sys
import time
from collections.abc import Callable
from pathlib import Path

import httpx

from tradedesk.desk import Desk
from tradedesk.notify import (
    Telegram,
    TelegramError,
    approval_buttons,
    digest,
    e,
    plan_text,
    status_text,
)

CONFIRM_SECONDS = 300
HELP = """<b>tradedesk</b>
/status equity, open positions and pending entries
/plans plans waiting for approval
/report the digest: equity over 24h, the latest run
/kill cancel every pending order, positions keep their stops
/flatten cancel every order and close every position
/help this list"""


class Bot:
    def __init__(
        self,
        desk: Desk,
        telegram: Telegram,
        offset_path: Path,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.time,
    ):
        self.desk = desk
        self.telegram = telegram
        self.offset_path = offset_path
        self.sleep = sleep
        self.clock = clock

    def offset(self) -> int:
        try:
            return int(self.offset_path.read_text().strip() or 0)
        except (FileNotFoundError, ValueError):
            return 0

    def save_offset(self, value: int) -> None:
        self.offset_path.parent.mkdir(parents=True, exist_ok=True)
        self.offset_path.write_text(str(value))

    def run(self, stop: Callable[[], bool] = lambda: False) -> None:
        failures = 0
        while not stop():
            try:
                self.poll()
                failures = 0
            except (httpx.HTTPError, TelegramError) as err:
                failures += 1
                delay = min(60, 2**failures)
                print(f"telegram: {err}, retrying in {delay}s", file=sys.stderr)
                self.sleep(delay)

    def poll(self, timeout: int = 50) -> int:
        updates = self.telegram.updates(self.offset(), timeout)
        for update in updates:
            try:
                self.handle(update)
            except Exception as err:
                print(f"telegram: update {update.get('update_id')} failed: {err}", file=sys.stderr)
            self.save_offset(update["update_id"] + 1)
        return len(updates)

    def mine(self, chat: dict | None) -> bool:
        """Only the owner's private chat. Groups are ignored even when their id matches."""
        return (
            chat is not None
            and chat.get("type") == "private"
            and str(chat.get("id")) == self.telegram.chat_id
        )

    def handle(self, update: dict) -> None:
        if "callback_query" in update:
            query = update["callback_query"]
            sender = str((query.get("from") or {}).get("id"))
            if (
                self.mine((query.get("message") or {}).get("chat"))
                and sender == self.telegram.chat_id
            ):
                self.callback(query)
            return
        message = update.get("message") or {}
        if self.mine(message.get("chat")):
            self.command((message.get("text") or "").strip())

    def command(self, text: str) -> None:
        name = text.split()[0].split("@")[0].lower() if text else ""
        if name == "/status":
            self.telegram.send(status_text(self.desk))
        elif name == "/plans":
            self.plans()
        elif name == "/report":
            self.telegram.send(digest(self.desk, html=True))
        elif name == "/kill":
            self.telegram.send(
                "Cancel every pending order? Open positions keep their stops.",
                [("Cancel orders", f"kill:{int(self.clock())}"), ("Keep", "keep:0")],
            )
        elif name == "/flatten":
            self.telegram.send(
                "Cancel every order and close every position at market?",
                [("Close everything", f"flatten:{int(self.clock())}"), ("Keep", "keep:0")],
            )
        else:
            self.telegram.send(HELP)

    def plans(self) -> None:
        rows = self.desk.db.all("SELECT * FROM plans WHERE status = 'proposed' ORDER BY id")
        if not rows:
            self.telegram.send("No plans waiting for approval.")
            return
        for plan in rows[:10]:
            self.telegram.send(
                plan_text(plan, self.desk.settings.quote), approval_buttons(plan["id"])
            )

    def callback(self, query: dict) -> None:
        action, _, arg = (query.get("data") or "").partition(":")
        message_id = query["message"]["message_id"]
        handler = {
            "approve": self._approve,
            "drop": self._drop,
            "kill": self._kill,
            "flatten": self._kill,
            "keep": self._keep,
        }.get(action)
        if handler is None or not arg.isdigit():
            self.telegram.answer(query["id"], "Unknown button")
            return
        note, text = handler(action, int(arg))
        self.telegram.answer(query["id"], note)
        self.telegram.edit(message_id, text)

    def _plan(self, plan_id: int) -> dict | None:
        return self.desk.db.one("SELECT * FROM plans WHERE id = ?", plan_id)

    def _approve(self, _: str, plan_id: int) -> tuple[str, str]:
        plan = self._plan(plan_id)
        if plan is None:
            return "No such plan", f"Plan {plan_id} doesn't exist."
        text = plan_text(plan, self.desk.settings.quote)
        try:
            self.desk.approve(plan_id)
        except ValueError:
            return "Not waiting", f"{text}\n\nAlready {e(plan['status'])}, nothing done."
        result = self.desk.execute(only=plan_id)
        detail = e("; ".join(result) or "approved, waiting for the next execute")
        return "Approved", f"{text}\n\n<b>Approved</b>, {detail}"

    def _drop(self, _: str, plan_id: int) -> tuple[str, str]:
        plan = self._plan(plan_id)
        if plan is None:
            return "No such plan", f"Plan {plan_id} doesn't exist."
        text = plan_text(plan, self.desk.settings.quote)
        if plan["status"] != "proposed":
            return "Not waiting", f"{text}\n\nAlready {e(plan['status'])}, nothing done."
        self.desk.reject(plan_id)
        return "Dropped", f"{text}\n\n<b>Dropped</b>"

    def _kill(self, action: str, asked_at: int) -> tuple[str, str]:
        if self.clock() - asked_at > CONFIRM_SECONDS:
            return "Too old", "That confirmation expired. Send the command again."
        flatten = action == "flatten"
        out = self.desk.kill(flatten)
        head = "Flattened" if flatten else "Orders cancelled"
        return head, f"<b>{head}</b>\n" + e("\n".join(out) or "nothing to cancel")

    def _keep(self, _: str, __: int) -> tuple[str, str]:
        return "Nothing done", "Left as it was."
