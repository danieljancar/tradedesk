"""Telegram messages for the desk owner: one listener on Desk.log, plus the daily digest."""

import os
import sys
from datetime import UTC, datetime, timedelta
from html import escape

import httpx

from tradedesk import learning
from tradedesk.desk import Desk

API = "https://api.telegram.org"
LIMIT = 3500
DIGEST_LIMIT = 1200


class TelegramError(RuntimeError):
    pass


class Telegram:
    def __init__(self, token: str, chat_id: str, http: httpx.Client | None = None):
        self.token = token
        self.chat_id = str(chat_id)
        self.http = http or httpx.Client(timeout=15)

    def call(self, method: str, payload: dict, wait: float | None = None) -> object:
        kw = {"timeout": wait} if wait else {}
        r = self.http.post(f"{API}/bot{self.token}/{method}", json=payload, **kw)
        try:
            data = r.json()
        except ValueError as e:
            raise TelegramError(f"{method}: HTTP {r.status_code}") from e
        if not data.get("ok"):
            raise TelegramError(f"{method}: {data.get('description', r.status_code)}")
        return data["result"]

    def send(self, text: str, buttons: list[tuple[str, str]] | None = None) -> int:
        payload = {"chat_id": self.chat_id, "text": text[:LIMIT], "parse_mode": "HTML"}
        if buttons:
            payload["reply_markup"] = keyboard(buttons)
        return self.call("sendMessage", payload)["message_id"]

    def edit(self, message_id: int, text: str) -> None:
        payload = {
            "chat_id": self.chat_id,
            "message_id": message_id,
            "text": text[:LIMIT],
            "parse_mode": "HTML",
        }
        self.call("editMessageText", payload)

    def answer(self, callback_id: str, text: str = "") -> None:
        self.call("answerCallbackQuery", {"callback_query_id": callback_id, "text": text[:180]})

    def updates(self, offset: int, timeout: int = 50) -> list[dict]:
        payload = {
            "offset": offset,
            "timeout": timeout,
            "allowed_updates": ["message", "callback_query"],
        }
        return self.call("getUpdates", payload, wait=timeout + 10)


def keyboard(buttons: list[tuple[str, str]]) -> dict:
    return {"inline_keyboard": [[{"text": t, "callback_data": d} for t, d in buttons]]}


def from_env(http: httpx.Client | None = None) -> Telegram | None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    return Telegram(token, chat_id, http) if token and chat_id else None


def e(value: object) -> str:
    return escape(str(value), quote=False)


def money(x: float | None) -> str:
    return f"{x or 0:.2f}"


def signed(x: float | None) -> str:
    return f"{x or 0:+.2f}"


def plan_text(plan: dict, quote: str) -> str:
    notional = (plan["qty"] or 0) * plan["entry"]
    lines = [
        f"<b>{e(plan['asset'])} {e(plan['side'])} {e(plan['horizon'])}</b>, plan {plan['id']}",
        f"entry {plan['entry']:g} ({e(plan['entry_type'])}), stop {plan['stop']:g}, "
        f"target {plan['take_profit']:g}",
        f"size {plan['qty'] or 0:g} ({money(notional)} {e(quote)}), risk "
        f"{money(plan['risk_amount'])}, R/R {plan['reward_risk']}"
        + (f", {plan['leverage']}x" if (plan["leverage"] or 1) > 1 else ""),
        f"confidence {plan['confidence']}",
    ]
    if plan.get("thesis"):
        lines.append(f"<i>{e(plan['thesis'][:400])}</i>")
    return "\n".join(lines)


def approval_buttons(plan_id: int) -> list[tuple[str, str]]:
    return [("Approve", f"approve:{plan_id}"), ("Drop", f"drop:{plan_id}")]


def ref_id(refs: list[str], prefix: str) -> int | None:
    for r in refs:
        if r.startswith(f"{prefix}:"):
            return int(r.split(":", 1)[1])
    return None


def no_stop(event: dict) -> bool:
    return event["kind"] == "error" and event["title"].startswith("No working stop")


def classify(event: dict) -> str | None:
    actor, kind = event["actor"], event["kind"]
    if actor == "risk" and kind == "pass":
        return "proposed"
    if actor == "exchange" and kind in ("fill", "exit", "error"):
        return kind
    if actor == "desk" and kind == "done":
        return "run"
    if actor == "desk" and kind == "kill":
        return "kill"
    return None


class Notifier:
    """Desk listener. Maps events to messages; a failed send prints one line and moves on."""

    def __init__(self, desk: Desk, telegram: Telegram, clock=None):
        self.desk = desk
        self.telegram = telegram
        self.clock = clock or datetime.now

    def __call__(self, event: dict) -> None:
        try:
            message = self.message(event)
            if message:
                self.telegram.send(*message)
        except Exception as err:
            print(f"telegram: {err}", file=sys.stderr)

    def message(self, event: dict) -> tuple[str, list[tuple[str, str]] | None] | None:
        name = classify(event)
        if name is None:
            return None
        cfg = self.desk.settings.notify
        urgent = no_stop(event)
        if not urgent and name not in cfg.events:
            return None
        build = getattr(self, f"_{name}")
        text, buttons, critical = build(event)
        if not urgent and not critical and cfg.quiet(self.clock().hour):
            return None
        return text, buttons

    def _plan(self, event: dict) -> dict | None:
        plan_id = ref_id(event["refs"], "plan")
        return self.desk.db.one("SELECT * FROM plans WHERE id = ?", plan_id) if plan_id else None

    def _position(self, event: dict) -> dict | None:
        pos_id = ref_id(event["refs"], "position")
        return self.desk.db.one("SELECT * FROM positions WHERE id = ?", pos_id) if pos_id else None

    def _proposed(self, event: dict):
        plan = self._plan(event)
        if plan is None:
            return f"<b>Passed risk</b>\n{e(event['title'])}", None, False
        text = plan_text(plan, self.desk.settings.quote)
        if self.desk.settings.execution.auto_execute:
            return (
                f"{text}\n\nPassed risk. auto_execute is on, it goes out with the run.",
                None,
                False,
            )
        return f"{text}\n\nPassed risk, waiting for you.", approval_buttons(plan["id"]), False

    def _fill(self, event: dict):
        pos = self._position(event)
        if pos is None:
            return f"<b>Filled</b>\n{e(event['title'])}", None, False
        text = (
            f"<b>{e(pos['asset'])} {e(pos['side'])} {e(pos['horizon'])} filled</b>\n"
            f"{pos['qty']:g} at {pos['entry_price']:g}, stop {pos['stop']:g} on the exchange, "
            f"target {pos['take_profit']:g}"
        )
        return text, None, False

    def _exit(self, event: dict):
        pos = self._position(event)
        if pos is None:
            return f"<b>Closed</b>\n{e(event['title'])}", None, False
        risk = abs(pos["entry_price"] - pos["initial_stop"]) * pos["qty"]
        r_mult = f" ({pos['pnl'] / risk:+.1f}R)" if risk and pos["pnl"] is not None else ""
        text = (
            f"<b>{e(pos['asset'])} {e(pos['side'])} {e(pos['horizon'])} closed</b> by "
            f"{e(pos['exit_reason'])}\n"
            f"entry {pos['entry_price']:g}, exit {pos['exit_price']:g}, pnl "
            f"{signed(pos['pnl'])}{r_mult}"
        )
        return text, None, pos["exit_reason"] == "stop"

    def _error(self, event: dict):
        head = "NO WORKING STOP" if no_stop(event) else "Exchange error"
        body = f"\n{e(event['body'][:600])}" if event.get("body") else ""
        return f"<b>{head}</b>\n{e(event['title'])}{body}", None, True

    def _run(self, event: dict):
        summary = (event.get("body") or "").strip()
        run = f"Run {e(event['run_id'])} done" if event.get("run_id") else "Run done"
        return f"<b>{run}</b>\n{e(summary[:1500])}".rstrip(), None, False

    def _kill(self, event: dict):
        body = (event.get("body") or "").strip() or "nothing to cancel"
        return f"<b>Kill switch</b>\n{e(body[:1500])}", None, False


def attach(desk: Desk, http: httpx.Client | None = None) -> Notifier | None:
    if not desk.settings.notify.telegram:
        return None
    telegram = from_env(http)
    if telegram is None:
        print(
            "telegram: notify is on but TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is empty",
            file=sys.stderr,
        )
        return None
    notifier = Notifier(desk, telegram)
    desk.listeners.append(notifier)
    return notifier


def equity_now(desk: Desk) -> float | None:
    try:
        value = desk.broker.equity()
    except Exception:
        row = desk.db.one("SELECT value FROM equity ORDER BY ts DESC LIMIT 1")
        return row["value"] if row else None
    desk.db.record_equity(value)
    return value


def equity_change(desk: Desk, value: float | None, hours: int = 24) -> float | None:
    if value is None:
        return None
    since = (datetime.now(UTC) - timedelta(hours=hours)).isoformat(timespec="seconds")
    row = desk.db.one("SELECT value FROM equity WHERE ts <= ? ORDER BY ts DESC LIMIT 1", since)
    row = row or desk.db.one("SELECT value FROM equity ORDER BY ts LIMIT 1")
    return value - row["value"] if row else None


def open_pnl(desk: Desk, pos: dict) -> float | None:
    try:
        price = desk.broker.price(pos["symbol"])
    except Exception:
        return None
    sign = 1 if pos["side"] == "long" else -1
    return (price - pos["entry_price"]) * pos["qty"] * sign


def position_lines(desk: Desk, html: bool = True) -> list[str]:
    out = []
    for p in desk.db.open_positions():
        pnl = open_pnl(desk, p)
        out.append(
            f"{_e(p['asset'], html)} {p['side']} {p['horizon']} {p['qty']:g} at "
            f"{p['entry_price']:g}, stop {p['stop']:g}, target {p['take_profit']:g}, open "
            + (signed(pnl) if pnl is not None else "n/a")
        )
    return out


def _e(value: object, html: bool) -> str:
    return e(value) if html else str(value)


def _b(text: str, html: bool) -> str:
    return f"<b>{text}</b>" if html else text


def status_text(desk: Desk) -> str:
    s = desk.settings
    value = equity_now(desk)
    day_start = datetime.now(UTC).replace(hour=0, minute=0, second=0).isoformat()
    lines = [
        _b(f"{s.mode} {s.market}", True)
        + f", equity {money(value) if value is not None else 'n/a'} {e(s.quote)}, realized today "
        + signed(desk.db.realized_since(day_start)),
        "Open positions:",
        *(position_lines(desk) or ["none"]),
        "Pending entries:",
        *(
            [
                f"plan {p['id']} {e(p['asset'])} {p['side']} {p['status']}, entry {p['entry']:g}"
                for p in desk.db.pending_plans()
            ]
            or ["none"]
        ),
    ]
    return "\n".join(lines)


def digest(desk: Desk, html: bool = False) -> str:
    s = desk.settings
    value = equity_now(desk)
    change = equity_change(desk, value)
    day_start = datetime.now(UTC).replace(hour=0, minute=0, second=0).isoformat()
    waiting = desk.db.all("SELECT * FROM plans WHERE status = 'proposed' ORDER BY id")
    head = f"Desk report, {s.mode} {s.market}"
    lines = [
        _b(head, html),
        f"equity {money(value) if value is not None else 'n/a'} {_e(s.quote, html)}"
        + (f" ({signed(change)} in 24h)" if change is not None else "")
        + f", realized today {signed(desk.db.realized_since(day_start))}",
    ]
    positions = position_lines(desk, html)
    lines.append(f"{len(positions)} open:" if positions else "no open positions")
    lines += positions[:6]
    if waiting:
        lines.append(f"{len(waiting)} plans waiting for approval:")
        lines += [
            f"plan {p['id']} {_e(p['asset'], html)} {p['side']} {p['horizon']}, entry "
            f"{p['entry']:g}, R/R {p['reward_risk']}"
            for p in waiting[:5]
        ]
    calibration = learning.summary_line(learning.stats(desk.db))
    if calibration:
        lines.append(_e(calibration, html))
    run = desk.db.latest_run()
    if run:
        used = len("\n".join(lines)) + 60
        summary = (run["summary"] or run["status"]).strip()
        room = max(80, DIGEST_LIMIT - used)
        if len(summary) > room:
            summary = summary[: room - 3].rstrip() + "..."
        lines.append(_b(f"Run {_e(run['id'], html)}", html))
        lines.append(_e(summary, html))
    return "\n".join(lines)
