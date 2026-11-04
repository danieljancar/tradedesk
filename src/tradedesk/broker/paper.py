from datetime import UTC, datetime

from tradedesk.binance.market import MarketData, SymbolRules
from tradedesk.broker.base import Exit, Fill, Placed, ms
from tradedesk.config import Market, Settings
from tradedesk.db import Database, now

FEE = 0.001


def iso(ms_value: int) -> str:
    return datetime.fromtimestamp(ms_value / 1000, UTC).isoformat(timespec="seconds")


class PaperBroker:
    """Simulated fills on live Binance candles. Stops win when stop and target sit in one candle."""

    def __init__(self, settings: Settings, md: MarketData, db: Database):
        self.settings = settings
        self.md = md
        self.db = db

    def price(self, symbol: str) -> float:
        return self.md.price(symbol)

    def rules(self, symbol: str) -> SymbolRules:
        return self.md.rules(symbol)

    def _unrealized(self) -> float:
        total = 0.0
        for p in self.db.open_positions():
            sign = 1 if p["side"] == "long" else -1
            total += (self.price(p["symbol"]) - p["entry_price"]) * p["qty"] * sign
        return total

    def equity(self) -> float:
        realized = self.db.one(
            "SELECT COALESCE(SUM(pnl), 0) AS v FROM positions WHERE status = 'closed'"
        )["v"]
        return self.settings.paper_equity + realized + self._unrealized()

    def free_quote(self) -> float:
        if self.settings.market is Market.FUTURES:
            return self.equity()
        held = sum(p["qty"] * p["entry_price"] for p in self.db.open_positions())
        waiting = sum(
            p["qty"] * p["entry"] for p in self.db.pending_plans() if p["status"] == "placed"
        )
        return self.equity() - held - waiting

    def place(self, plan: dict) -> Placed:
        if plan["entry_type"] == "market":
            price = self.price(plan["symbol"])
            return Placed(open=True, fill_price=price, qty=plan["qty"], refs={"paper": True})
        return Placed(open=False, refs={"paper": True, "placed_at": now()})

    def _candles(self, symbol: str, since: str):
        return self.md.klines(symbol, "1h", 1000, start_ms=ms(since))

    def entry_status(self, plan: dict) -> Fill | str | None:
        sign = 1 if plan["side"] == "long" else -1
        for c in self._candles(plan["symbol"], plan["updated_at"]):
            touched = c.low <= plan["entry"] if sign > 0 else c.high >= plan["entry"]
            if touched:
                return Fill(price=plan["entry"], qty=plan["qty"], at=iso(c.open_time))
        return None

    def exit_status(self, position: dict) -> Exit | None:
        sign = 1 if position["side"] == "long" else -1
        stop, target = position["stop"], position["take_profit"]
        for c in self._candles(position["symbol"], position["opened_at"]):
            stop_hit = c.low <= stop if sign > 0 else c.high >= stop
            target_hit = c.high >= target if sign > 0 else c.low <= target
            if stop_hit:
                fill = min(c.open, stop) if sign > 0 else max(c.open, stop)
                return self._exit(position, fill, "stop")
            if target_hit:
                return self._exit(position, target, "target")
        return None

    def _exit(self, position: dict, price: float, reason: str) -> Exit:
        sign = 1 if position["side"] == "long" else -1
        gross = (price - position["entry_price"]) * position["qty"] * sign
        fees = (price + position["entry_price"]) * position["qty"] * FEE
        return Exit(price=price, reason=reason, pnl=gross - fees)

    def cancel(self, plan: dict) -> Fill | None:
        return None

    def close(self, position: dict) -> Exit:
        return self._exit(position, self.price(position["symbol"]), "manual")

    def move_stop(self, position: dict, stop: float) -> dict:
        return {"paper": True}
