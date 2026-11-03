import json
from contextlib import suppress

from tradedesk.binance.client import BinanceError, Client
from tradedesk.binance.market import MarketData, SymbolRules
from tradedesk.broker.base import Exit, Fill, Placed, ms
from tradedesk.config import Settings
from tradedesk.db import now


class FuturesBroker:
    """USDT-M futures, one-way mode, isolated margin.

    Entries are market orders only, sent when price reaches the plan's entry. Stop and target
    go out right after the fill as conditional closePosition orders. If the stop can't be
    placed, the position is closed at once.
    """

    def __init__(self, settings: Settings, client: Client, md: MarketData):
        self.settings = settings
        self.client = client
        self.md = md

    def price(self, symbol: str) -> float:
        return self.md.price(symbol)

    def rules(self, symbol: str) -> SymbolRules:
        return self.md.rules(symbol)

    def _account(self) -> dict:
        return self.client.signed("GET", "/fapi/v3/account")

    def equity(self) -> float:
        return float(self._account()["totalMarginBalance"])

    def free_quote(self) -> float:
        return float(self._account()["availableBalance"])

    def _prepare(self, symbol: str, leverage: int) -> None:
        try:
            self.client.signed("POST", "/fapi/v1/marginType", symbol=symbol, marginType="ISOLATED")
        except BinanceError as e:
            if e.code != -4046:
                raise
        self.client.signed("POST", "/fapi/v1/leverage", symbol=symbol, leverage=leverage)

    def _conditional(self, symbol: str, side: str, kind: str, trigger: float) -> int:
        order = self.client.signed(
            "POST",
            "/fapi/v1/algoOrder",
            algoType="CONDITIONAL",
            symbol=symbol,
            side=side,
            type=kind,
            triggerPrice=trigger,
            closePosition=True,
            workingType="MARK_PRICE",
            priceProtect=True,
        )
        return order["algoId"]

    def _market(self, symbol: str, side: str, qty: float, reduce: bool = False) -> dict:
        return self.client.signed(
            "POST",
            "/fapi/v1/order",
            symbol=symbol,
            side=side,
            type="MARKET",
            quantity=qty,
            reduceOnly=reduce or None,
            newOrderRespType="RESULT",
        )

    def _protect(self, symbol: str, side: str, stop: float, target: float) -> dict:
        exit_side = "SELL" if side == "long" else "BUY"
        return {
            "stop": self._conditional(symbol, exit_side, "STOP_MARKET", stop),
            "target": self._conditional(symbol, exit_side, "TAKE_PROFIT_MARKET", target),
        }

    def _open(self, plan: dict) -> Placed:
        symbol, side = plan["symbol"], plan["side"]
        self._prepare(symbol, plan["leverage"] or 1)
        order = self._market(symbol, "BUY" if side == "long" else "SELL", plan["qty"])
        fill, qty = float(order["avgPrice"]), float(order["executedQty"])
        try:
            refs = self._protect(symbol, side, plan["stop"], plan["take_profit"])
        except BinanceError:
            self._market(symbol, "SELL" if side == "long" else "BUY", qty, reduce=True)
            raise
        return Placed(open=True, fill_price=fill, qty=qty, refs=refs)

    def place(self, plan: dict) -> Placed:
        if plan["entry_type"] == "market":
            return self._open(plan)
        return Placed(open=False, refs={"waiting": True})

    def entry_status(self, plan: dict) -> Fill | str | None:
        price = self.price(plan["symbol"])
        sign = 1 if plan["side"] == "long" else -1
        if (price - plan["entry"]) * sign > 0:
            return None
        if (price - plan["stop"]) * sign <= 0:
            return "cancelled"
        placed = self._open(plan | {"entry_type": "market"})
        return Fill(
            price=placed.fill_price or price, qty=placed.qty or 0, at=now(), refs=placed.refs
        )

    def _cancel_algo(self, algo_id: int) -> None:
        with suppress(BinanceError):
            self.client.signed("DELETE", "/fapi/v1/algoOrder", algoId=algo_id)

    def exit_status(self, position: dict) -> Exit | None:
        symbol = position["symbol"]
        risk = self.client.signed("GET", "/fapi/v3/positionRisk", symbol=symbol)
        if any(abs(float(p["positionAmt"])) > 0 for p in risk):
            return None
        refs = json.loads(position["exchange"])
        for leg in ("stop", "target"):
            self._cancel_algo(refs[leg])
        trades = self.client.signed(
            "GET", "/fapi/v1/userTrades", symbol=symbol, startTime=ms(position["opened_at"])
        )
        exit_side = "SELL" if position["side"] == "long" else "BUY"
        exits = [t for t in trades if t["side"] == exit_side]
        qty = sum(float(t["qty"]) for t in exits)
        price = sum(float(t["price"]) * float(t["qty"]) for t in exits) / qty if qty else 0.0
        pnl = sum(float(t["realizedPnl"]) - float(t["commission"]) for t in exits)
        reason = (
            "stop"
            if abs(price - position["stop"]) < abs(price - position["take_profit"])
            else "target"
        )
        return Exit(price=price, reason=reason, pnl=pnl)

    def cancel(self, plan: dict) -> None:
        return None

    def close(self, position: dict) -> Exit:
        refs = json.loads(position["exchange"])
        for leg in ("stop", "target"):
            self._cancel_algo(refs[leg])
        side = "SELL" if position["side"] == "long" else "BUY"
        order = self._market(position["symbol"], side, position["qty"], reduce=True)
        price = float(order["avgPrice"])
        sign = 1 if position["side"] == "long" else -1
        return Exit(
            price=price,
            reason="manual",
            pnl=(price - position["entry_price"]) * position["qty"] * sign,
        )

    def move_stop(self, position: dict, stop: float) -> dict:
        refs = json.loads(position["exchange"])
        exit_side = "SELL" if position["side"] == "long" else "BUY"
        new_id = self._conditional(position["symbol"], exit_side, "STOP_MARKET", stop)
        self._cancel_algo(refs["stop"])
        return refs | {"stop": new_id}
