import json
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from pathlib import Path

from tradedesk import learning, news, notes, risk, snapshot, universe
from tradedesk.binance import market_data
from tradedesk.broker import Broker, Fill, make_broker
from tradedesk.broker.base import Unprotected
from tradedesk.config import Horizon, Market, Settings
from tradedesk.db import Database, now
from tradedesk.models import PlanFile, TradeIdea


class Desk:
    def __init__(self, settings: Settings, db: Database, broker: Broker | None = None):
        self.settings = settings
        self.db = db
        self._broker = broker

    @property
    def broker(self) -> Broker:
        if self._broker is None:
            self._broker = make_broker(self.settings, self.db)
        return self._broker

    def run_id(self) -> str | None:
        run = self.db.latest_run()
        return run["id"] if run else None

    def run_dir(self, run_id: str) -> Path:
        path = self.settings.path(self.settings.runs_dir) / run_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def log(self, actor: str, kind: str, title: str, body: str | None = None, refs=None) -> None:
        self.db.log(self.run_id(), actor, kind, title, body, refs)

    def start_run(self) -> str:
        run_id = datetime.now(UTC).strftime("%Y-%m-%dT%H%M")
        if self.db.one("SELECT id FROM runs WHERE id = ?", run_id) is None:
            self.db.insert("runs", id=run_id, started_at=now())
        self.run_dir(run_id)
        mode = f"{self.settings.mode} {self.settings.market}"
        self.log("desk", "start", f"Run {run_id} started ({mode})")
        return run_id

    def finish_run(self, summary: str) -> None:
        run_id = self.run_id()
        if run_id:
            self.db.update("runs", run_id, finished_at=now(), status="done", summary=summary)
            self.log("desk", "done", "Run finished", summary)

    def post(self, actor: str, file: Path | None, start: bool = False, reads=None) -> None:
        if start:
            self.log(actor, "start", f"{actor} is working", refs=reads)
            return
        body = file.read_text() if file else ""
        first = next((ln.strip("# ").strip() for ln in body.splitlines() if ln.strip()), actor)
        self.log(actor, "output", first[:140], body, refs=reads)

    def write_universe(self, extra: Iterable[str] = ()) -> Path:
        run_dir = self.run_dir(self.run_id() or self.start_run())
        if not self.settings.universe.enabled:
            assets = universe.watchlist(self.settings)
            universe.write(run_dir, assets)
            self.log("scanner", "output", "Scan is off, using the watchlist")
            return run_dir / "universe.md"
        self.log("scanner", "start", f"Scanning {self.settings.quote} spot pairs")
        try:
            scanned = universe.scan(self.settings, market_data(self.settings))
        except Exception as e:
            self.log("scanner", "error", "Scan failed, watchlist and fixed assets only", str(e))
            scanned = []
        assets = universe.assets_for_run(self.settings, scanned, extra)
        text = universe.write(run_dir, assets)
        found = [a["asset"] for a in assets if a["source"] == "scan"]
        title = f"{len(assets)} assets, from the scan: {', '.join(found) or 'none'}"
        self.log("scanner", "output", title, text)
        return run_dir / "universe.md"

    def run_assets(self) -> list[dict]:
        run_id = self.run_id()
        saved = universe.read(self.run_dir(run_id)) if run_id else None
        if not saved or not self.settings.universe.enabled:
            return universe.watchlist(self.settings)
        return saved

    def write_snapshot(self) -> Path:
        run_dir = self.run_dir(self.run_id() or self.start_run())
        assets = self.run_assets()
        self.log("prices", "start", "Pulling candles, funding and open interest")
        text, facts = snapshot.build(self.settings, market_data(self.settings), assets)
        (run_dir / "snapshot.md").write_text(text)
        (run_dir / "facts.json").write_text(json.dumps(facts))
        learning.store_snapshot(self.db, run_dir.name, facts)
        names = ", ".join(a["asset"] for a in assets)
        self.log("prices", "output", f"Snapshot for {names}", text)
        return run_dir / "snapshot.md"

    def write_news(self) -> Path:
        run_dir = self.run_dir(self.run_id() or self.start_run())
        self.log("headlines", "start", "Reading news feeds")
        text = news.build(self.settings.news_feeds, [a["asset"] for a in self.run_assets()])
        (run_dir / "news.md").write_text(text)
        count = sum(1 for ln in text.splitlines() if ln.startswith("- ["))
        self.log("headlines", "output", f"{count} headlines sorted by asset", text)
        return run_dir / "news.md"

    def book(self) -> risk.Book:
        equity = self.broker.equity()
        self.db.record_equity(equity)
        open_risk, taken = 0.0, set()
        for p in self.db.open_positions():
            sign = 1 if p["side"] == "long" else -1
            open_risk += max(0.0, (p["entry_price"] - p["stop"]) * sign) * p["qty"]
            taken.add((p["asset"], p["horizon"]))
        pending = self.db.pending_plans()
        for p in pending:
            open_risk += p["risk_amount"] or 0
            taken.add((p["asset"], p["horizon"]))
        allowed = {a["asset"] for a in self.run_assets()} | {a for a, _ in taken}
        day_start = datetime.now(UTC).replace(hour=0, minute=0, second=0).isoformat()
        return risk.Book(
            equity=equity,
            free_quote=self.broker.free_quote(),
            peak_equity=self.db.peak_equity() or equity,
            day_pnl=self.db.realized_since(day_start),
            open_risk=open_risk,
            open_count=len(self.db.open_positions()) + len(pending),
            taken=taken,
            allowed=allowed,
        )

    def write_book(self) -> Path:
        run_dir = self.run_dir(self.run_id() or self.start_run())
        b = self.book()
        limits = self.settings.risk
        lines = [
            f"# Book ({self.settings.mode} {self.settings.market}, quote {self.settings.quote})",
            f"equity {b.equity:.2f} | free {b.free_quote:.2f} | peak {b.peak_equity:.2f} | "
            f"realized today {b.day_pnl:+.2f} | open risk {b.open_risk:.2f} "
            f"({b.open_risk / b.equity * 100:.1f}% of {limits.max_total_risk_pct}%)",
            f"rules: risk {limits.risk_per_trade_pct}% per trade, min reward/risk "
            f"{limits.min_reward_risk}, max {limits.max_open_positions} positions, "
            f"min confidence {limits.min_confidence}, shorts "
            f"{'allowed' if self.settings.market == 'futures' else 'not allowed (spot)'}",
            "max hold days: "
            + ", ".join(f"{k} {v}" for k, v in self.settings.hold_days.model_dump().items()),
        ]
        blocks = risk.account_blocks(self.settings, b)
        if blocks:
            lines.append("NEW TRADES BLOCKED: " + "; ".join(blocks))
        lines.append("## Open positions")
        opened = self.db.open_positions()
        for p in opened:
            price = self.broker.price(p["symbol"])
            sign = 1 if p["side"] == "long" else -1
            r_mult = (price - p["entry_price"]) * sign / abs(p["entry_price"] - p["initial_stop"])
            days = (datetime.now(UTC) - datetime.fromisoformat(p["opened_at"])).days
            lines.append(
                f"- id {p['id']} {p['asset']} {p['side']} {p['horizon']} | entry "
                f"{p['entry_price']:.6g} now {price:.6g} ({r_mult:+.2f}R) | stop {p['stop']:.6g} "
                f"target {p['take_profit']:.6g} | held {days}d"
            )
        if not opened:
            lines.append("- none (flat)")
        lines.append("## Pending entries")
        for p in self.db.pending_plans():
            lines.append(
                f"- plan {p['id']} {p['asset']} {p['side']} {p['horizon']} entry {p['entry']:.6g} "
                f"stop {p['stop']:.6g} target {p['take_profit']:.6g} ({p['status']})"
            )
        lines.append("## Last closed trades")
        closed = self.db.all(
            "SELECT * FROM positions WHERE status = 'closed' ORDER BY closed_at DESC LIMIT 8"
        )
        for p in closed:
            lines.append(
                f"- {p['closed_at'][:10]} {p['asset']} {p['side']} {p['horizon']} "
                f"{p['exit_reason']} pnl {p['pnl']:+.2f}"
            )
        if not closed:
            lines.append("- none yet")
        lines += notes.book_lines(self.db)
        lessons = self.settings.path(Path("lessons.md"))
        lines.append("## Lessons from past reviews")
        calibration = learning.summary_line(learning.stats(self.db))
        if calibration:
            lines.append(f"- {calibration}")
        lines.append(lessons.read_text().strip() if lessons.exists() else "- none yet")
        text = "\n".join(lines) + "\n"
        (run_dir / "book.md").write_text(text)
        self.log("book", "output", f"Equity {b.equity:.2f}, {len(opened)} open", text)
        return run_dir / "book.md"

    def _facts(self) -> dict:
        run_id = self.run_id()
        path = self.run_dir(run_id) / "facts.json" if run_id else None
        return json.loads(path.read_text()) if path and path.exists() else {}

    def check_plans(self, file: Path) -> list[dict]:
        run_id = self.run_id()
        plan_file = PlanFile.model_validate_json(file.read_text())
        self.log("risk", "start", f"Checking {len(plan_file.ideas)} ideas against the rules")
        facts, book, results = self._facts(), self.book(), []
        for idea in plan_file.ideas:
            results.append(self._check_idea(run_id, idea, book, facts))
        for action in plan_file.position_actions:
            results.append(self._position_action(action.model_dump()))
        if self.settings.execution.auto_execute:
            for r in results:
                if r.get("status") == "proposed":
                    self.approve(r["id"])
        passed = sum(r.get("status") in ("proposed", "approved") for r in results)
        failed = sum(r.get("status") == "rejected" for r in results)
        summary = f"{passed} passed, {failed} rejected" if results else "Nothing to check"
        self.log("risk", "reject" if failed and not passed else "output", summary)
        return results

    def _check_idea(self, run_id, idea: TradeIdea, book: risk.Book, facts: dict) -> dict:
        symbol = self.settings.symbol(idea.asset)
        try:
            price = self.broker.price(symbol)
            rules = self.broker.rules(symbol)
        except Exception as e:
            verdict = risk.Verdict(False, [f"no market data: {e}"])
        else:
            atr = risk.horizon_atr(idea.horizon, facts.get(idea.asset, {}))
            verdict = risk.check(idea, self.settings, book, price, atr, rules)
        status = "proposed" if verdict.ok else "rejected"
        plan_id = self.db.insert(
            "plans",
            run_id=run_id,
            asset=idea.asset,
            symbol=symbol,
            horizon=idea.horizon.value,
            side=idea.side.value,
            rating=idea.rating.value,
            entry_type=idea.entry_type,
            entry=verdict.entry or idea.entry,
            stop=verdict.stop or idea.stop,
            take_profit=verdict.take_profit or idea.take_profit,
            confidence=idea.confidence,
            thesis=idea.thesis,
            invalidation=idea.invalidation,
            status=status,
            reasons="; ".join(verdict.reasons),
            qty=verdict.qty,
            risk_amount=verdict.risk_amount,
            reward_risk=verdict.reward_risk,
            leverage=verdict.leverage,
            created_at=now(),
            updated_at=now(),
        )
        if verdict.ok:
            book.open_count += 1
            book.open_risk += verdict.risk_amount
            book.free_quote -= verdict.notional
            book.taken.add((idea.asset, idea.horizon.value))
            title = (
                f"Passed: {idea.asset} {idea.side} {idea.horizon}, {verdict.qty:g} at "
                f"{verdict.entry:g}, risk {verdict.risk_amount:.2f}, R/R {verdict.reward_risk}"
            )
        else:
            title = f"Rejected: {idea.asset} {idea.side} {idea.horizon}"
        self.log(
            "risk",
            "pass" if verdict.ok else "reject",
            title,
            "\n".join(verdict.reasons),
            refs=[f"plan:{plan_id}"],
        )
        return {
            "id": plan_id,
            "asset": idea.asset,
            "status": status,
            "reasons": verdict.reasons,
            "qty": verdict.qty,
            "risk": verdict.risk_amount,
            "rr": verdict.reward_risk,
        }

    def _position_action(self, action: dict) -> dict:
        pos = self.db.one(
            "SELECT * FROM positions WHERE id = ? AND status = 'open'", action["position_id"]
        )
        if pos is None:
            return {
                "position": action["position_id"],
                "status": "rejected",
                "reasons": ["no open position with that id"],
            }
        if action["action"] == "close":
            self.close(pos["id"], action["reason"])
            return {"position": pos["id"], "status": "closed", "reasons": []}
        return self.tighten(pos["id"], action["stop"], action["reason"])

    def tighten(self, position_id: int, stop: float | None, reason: str = "") -> dict:
        pos = self.db.one("SELECT * FROM positions WHERE id = ?", position_id)
        sign = 1 if pos["side"] == "long" else -1
        price = self.broker.price(pos["symbol"])
        stop = self.broker.rules(pos["symbol"]).price(stop or 0)
        problems = []
        if (stop - pos["stop"]) * sign <= 0:
            problems.append("stops only move in the trade's favor")
        if (price - stop) * sign <= 0:
            problems.append("new stop is through the current price")
        if problems:
            self.log("risk", "reject", f"Stop move on {pos['asset']} refused", "\n".join(problems))
            return {"position": position_id, "status": "rejected", "reasons": problems}
        refs = self.broker.move_stop(pos, stop)
        self.db.update("positions", position_id, stop=stop, exchange=json.dumps(refs))
        self.log("exchange", "order", f"Stop on {pos['asset']} moved to {stop:g}", reason)
        return {"position": position_id, "status": "tightened", "reasons": []}

    def approve(self, plan_id: int) -> None:
        plan = self.db.one("SELECT * FROM plans WHERE id = ?", plan_id)
        if plan is None or plan["status"] != "proposed":
            raise ValueError(f"plan {plan_id} is not waiting for approval")
        self.db.update("plans", plan_id, status="approved", updated_at=now())
        self.log("desk", "approve", f"Plan {plan_id} approved ({plan['asset']} {plan['side']})")

    def reject(self, plan_id: int) -> None:
        self.db.update("plans", plan_id, status="cancelled", updated_at=now())
        self.log("desk", "reject", f"Plan {plan_id} dropped")

    def execute(self) -> list[str]:
        out = []
        for plan in self.db.all("SELECT * FROM plans WHERE status = 'approved'"):
            if plan["exchange"]:
                continue
            try:
                placed = self.broker.place(plan)
            except Exception as e:
                self.db.update(
                    "plans",
                    plan["id"],
                    status="rejected",
                    reasons=f"exchange: {e}",
                    updated_at=now(),
                )
                self.log("exchange", "error", f"Order for plan {plan['id']} failed", str(e))
                out.append(f"plan {plan['id']}: failed, {e}")
                continue
            self.db.update(
                "plans",
                plan["id"],
                status="placed",
                exchange=json.dumps(placed.refs),
                updated_at=now(),
            )
            if placed.open:
                self._open_position(
                    plan,
                    Fill(
                        placed.fill_price or plan["entry"],
                        placed.qty or plan["qty"],
                        now(),
                        placed.refs,
                    ),
                )
                out.append(f"plan {plan['id']}: filled at {placed.fill_price}")
            else:
                self.log(
                    "exchange",
                    "order",
                    f"Limit entry for {plan['asset']} at {plan['entry']:g} with stop "
                    f"{plan['stop']:g} and target {plan['take_profit']:g} on the exchange",
                )
                out.append(f"plan {plan['id']}: entry order resting at {plan['entry']}")
        return out

    def _open_position(self, plan: dict, fill: Fill) -> int:
        position_id = self.db.insert(
            "positions",
            plan_id=plan["id"],
            symbol=plan["symbol"],
            asset=plan["asset"],
            horizon=plan["horizon"],
            side=plan["side"],
            qty=fill.qty,
            entry_price=fill.price,
            stop=plan["stop"],
            take_profit=plan["take_profit"],
            initial_stop=plan["stop"],
            opened_at=fill.at,
            exchange=json.dumps(fill.refs or json.loads(plan["exchange"] or "{}")),
        )
        self.db.update("plans", plan["id"], status="open", updated_at=now())
        self.log(
            "exchange",
            "fill",
            f"{plan['asset']} {plan['side']} filled {fill.qty:g} at {fill.price:g}, stop "
            f"{plan['stop']:g} live on the exchange",
            refs=[f"position:{position_id}"],
        )
        return position_id

    def sync(self) -> list[str]:
        out = []
        for plan in self.db.all("SELECT * FROM plans WHERE status = 'placed'"):
            try:
                out += self._sync_entry(plan)
            except Exception as e:
                self.log("exchange", "error", f"Entry check for plan {plan['id']} failed", str(e))
                if self.settings.market is Market.FUTURES:
                    self.db.update(
                        "plans",
                        plan["id"],
                        status="rejected",
                        reasons=f"exchange: {e}",
                        updated_at=now(),
                    )
                out.append(f"plan {plan['id']}: error, {e}")
        for pos in self.db.open_positions():
            try:
                out += self._sync_position(pos)
            except Unprotected as e:
                self.log("exchange", "error", f"No working stop on {pos['asset']}", str(e))
                out.append(f"position {pos['id']}: NO STOP ON THE EXCHANGE, {e}")
            except Exception as e:
                self.log("exchange", "error", f"Check on {pos['asset']} failed", str(e))
                out.append(f"position {pos['id']}: error, {e}")
        self.db.record_equity(self.broker.equity())
        try:
            self.learn(stale_after=timedelta(hours=1))
        except Exception as e:
            self.log("desk", "error", "Outcome update failed", str(e))
        return out

    def learn(self, stale_after: timedelta | None = None) -> dict:
        """Replay every unresolved idea on real 1h candles and record what the market did."""
        return learning.learn(self.db, self.settings, market_data(self.settings), stale_after)

    def _sync_entry(self, plan: dict) -> list[str]:
        status = self.broker.entry_status(plan)
        if isinstance(status, Fill):
            self._open_position(plan, status)
            return [f"plan {plan['id']} filled at {status.price:g}"]
        if status == "cancelled":
            self.db.update("plans", plan["id"], status="cancelled", updated_at=now())
            return [f"plan {plan['id']} cancelled by the exchange"]
        ttl = timedelta(hours=self.settings.execution.entry_ttl_hours)
        if datetime.now(UTC) - datetime.fromisoformat(plan["updated_at"]) <= ttl:
            return []
        partial = self.broker.cancel(plan)
        if partial:
            self._open_position(plan, partial)
            return [f"plan {plan['id']} expired part filled, {partial.qty:g} kept with its stop"]
        self.db.update("plans", plan["id"], status="expired", updated_at=now())
        self.log("exchange", "cancel", f"Entry for {plan['asset']} expired unfilled")
        return [f"plan {plan['id']} expired"]

    def _sync_position(self, pos: dict) -> list[str]:
        exit_ = self.broker.exit_status(pos)
        if exit_:
            self._close_position(pos, exit_.price, exit_.reason, exit_.pnl)
            return [f"position {pos['id']} closed by {exit_.reason} at {exit_.price:g}"]
        max_days = self.settings.hold_days.days(Horizon(pos["horizon"]))
        held = datetime.now(UTC) - datetime.fromisoformat(pos["opened_at"])
        if self.settings.execution.close_expired and held > timedelta(days=max_days):
            self.close(pos["id"], f"held longer than {max_days} days")
            return [f"position {pos['id']} closed, hold time ran out"]
        return []

    def _close_position(self, pos: dict, price: float, reason: str, pnl: float | None) -> None:
        sign = 1 if pos["side"] == "long" else -1
        pnl = pnl if pnl is not None else (price - pos["entry_price"]) * pos["qty"] * sign
        self.db.update(
            "positions",
            pos["id"],
            status="closed",
            closed_at=now(),
            exit_price=price,
            pnl=pnl,
            exit_reason=reason,
        )
        self.db.update("plans", pos["plan_id"], status="closed", updated_at=now())
        self.log(
            "exchange",
            "exit",
            f"{pos['asset']} closed at {price:g} ({reason}), pnl {pnl:+.2f}",
            refs=[f"position:{pos['id']}"],
        )

    def close(self, position_id: int, reason: str = "manual") -> None:
        pos = self.db.one("SELECT * FROM positions WHERE id = ? AND status = 'open'", position_id)
        if pos is None:
            raise ValueError(f"position {position_id} is not open")
        exit_ = self.broker.close(pos)
        self._close_position(pos, exit_.price, reason, exit_.pnl)

    def kill(self, flatten: bool) -> list[str]:
        out = []
        for plan in self.db.all(
            "SELECT * FROM plans WHERE status IN ('proposed','approved','placed')"
        ):
            partial = self.broker.cancel(plan) if plan["status"] == "placed" else None
            if partial:
                self._open_position(plan, partial)
                out.append(f"plan {plan['id']} had a partial fill, now a position")
                continue
            self.db.update("plans", plan["id"], status="cancelled", updated_at=now())
            out.append(f"plan {plan['id']} cancelled")
        if flatten:
            for pos in self.db.open_positions():
                self.close(pos["id"], "kill switch")
                out.append(f"position {pos['id']} closed")
        self.log("desk", "kill", "Kill switch", "\n".join(out))
        return out
