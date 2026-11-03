import json

from tradedesk.binance.client import BinanceError, Client
from tradedesk.binance.market import MarketData, SymbolRules
from tradedesk.broker.base import Exit, Fill, Placed
from tradedesk.config import Settings
from tradedesk.db import now

FEE_BUFFER = 0.0015


def avg_price(order: dict) -> float:
    qty = float(order["executedQty"])
    return float(order["cummulativeQuoteQty"]) / qty if qty else 0.0


class SpotBroker:
    """Long-only spot. Every entry carries an exchange-side stop and target (OTOCO or OCO)."""

    def __init__(self, settings: Settings, client: Client, md: MarketData):
        self.settings = settings
        self.client = client
        self.md = md

    def price(self, symbol: str) -> float:
        return self.md.price(symbol)

    def rules(self, symbol: str) -> SymbolRules:
        return self.md.rules(symbol)

    def _balances(self) -> dict[str, float]:
        account = self.client.signed("GET", "/api/v3/account", omitZeroBalances=True)
        return {b["asset"]: float(b["free"]) + float(b["locked"]) for b in account["balances"]} | {
            f"{b['asset']}:free": float(b["free"]) for b in account["balances"]
        }

    def equity(self) -> float:
        bal = self._balances()
        total = bal.get(self.settings.quote, 0.0)
        for asset in self.settings.watchlist:
            amount = bal.get(asset.upper(), 0.0)
            if amount:
                total += amount * self.price(self.settings.symbol(asset))
        return total

    def free_quote(self) -> float:
        return self._balances().get(f"{self.settings.quote}:free", 0.0)

    def _exit_qty(self, symbol: str, qty: float) -> float:
        return self.rules(symbol).qty(qty * (1 - FEE_BUFFER))

    def _oco(self, symbol: str, qty: float, stop: float, target: float) -> dict:
        report = self.client.signed(
            "POST",
            "/api/v3/orderList/oco",
            symbol=symbol,
            side="SELL",
            quantity=qty,
            aboveType="LIMIT_MAKER",
            abovePrice=target,
            belowType="STOP_LOSS",
            belowStopPrice=stop,
            newOrderRespType="RESULT",
        )
        return {"list": report["orderListId"], **self._legs(report)}

    @staticmethod
    def _legs(report: dict) -> dict:
        legs = {}
        for o in report.get("orderReports", []):
            kind = {"LIMIT": "entry", "LIMIT_MAKER": "target", "STOP_LOSS": "stop"}.get(o["type"])
            if kind:
                legs[kind] = o["orderId"]
        return legs

    def place(self, plan: dict) -> Placed:
        symbol, qty = plan["symbol"], plan["qty"]
        exit_qty = self._exit_qty(symbol, qty)
        if plan["entry_type"] == "market":
            order = self.client.signed(
                "POST",
                "/api/v3/order",
                symbol=symbol,
                side="BUY",
                type="MARKET",
                quantity=qty,
                newOrderRespType="FULL",
            )
            fill = avg_price(order)
            try:
                refs = self._oco(symbol, exit_qty, plan["stop"], plan["take_profit"])
            except BinanceError:
                self.client.signed(
                    "POST",
                    "/api/v3/order",
                    symbol=symbol,
                    side="SELL",
                    type="MARKET",
                    quantity=exit_qty,
                )
                raise
            return Placed(open=True, fill_price=fill, qty=exit_qty, refs=refs)
        report = self.client.signed(
            "POST",
            "/api/v3/orderList/otoco",
            symbol=symbol,
            workingType="LIMIT",
            workingSide="BUY",
            workingPrice=plan["entry"],
            workingQuantity=qty,
            workingTimeInForce="GTC",
            pendingSide="SELL",
            pendingQuantity=exit_qty,
            pendingAboveType="LIMIT_MAKER",
            pendingAbovePrice=plan["take_profit"],
            pendingBelowType="STOP_LOSS",
            pendingBelowStopPrice=plan["stop"],
            newOrderRespType="RESULT",
        )
        refs = {"list": report["orderListId"], **self._legs(report)}
        if not {"entry", "stop", "target"} <= refs.keys():
            refs |= self._resolve_legs(symbol, report["orderListId"])
        return Placed(open=False, refs=refs)

    def _resolve_legs(self, symbol: str, list_id: int) -> dict:
        listing = self.client.signed("GET", "/api/v3/orderList", orderListId=list_id)
        legs = {}
        for o in listing["orders"]:
            legs |= self._legs({"orderReports": [self._order(symbol, o["orderId"])]})
        return legs

    def _order(self, symbol: str, order_id: int) -> dict:
        return self.client.signed("GET", "/api/v3/order", symbol=symbol, orderId=order_id)

    def entry_status(self, plan: dict) -> Fill | str | None:
        refs = json.loads(plan["exchange"])
        order = self._order(plan["symbol"], refs["entry"])
        if order["status"] == "FILLED":
            qty = self._exit_qty(plan["symbol"], float(order["executedQty"]))
            return Fill(price=avg_price(order), qty=qty, at=now(), refs=refs)
        if order["status"] in ("CANCELED", "EXPIRED", "REJECTED", "EXPIRED_IN_MATCH"):
            return "cancelled"
        return None

    def exit_status(self, position: dict) -> Exit | None:
        refs = json.loads(position["exchange"])
        for leg in ("stop", "target"):
            order = self._order(position["symbol"], refs[leg])
            if order["status"] == "FILLED":
                price = avg_price(order)
                pnl = (price - position["entry_price"]) * float(order["executedQty"])
                return Exit(price=price, reason=leg, pnl=pnl)
        return None

    def _cancel_list(self, symbol: str, list_id: int) -> None:
        try:
            self.client.signed("DELETE", "/api/v3/orderList", symbol=symbol, orderListId=list_id)
        except BinanceError as e:
            if e.code != -2011:
                raise

    def cancel(self, plan: dict) -> None:
        self._cancel_list(plan["symbol"], json.loads(plan["exchange"])["list"])

    def close(self, position: dict) -> Exit:
        self._cancel_list(position["symbol"], json.loads(position["exchange"])["list"])
        order = self.client.signed(
            "POST",
            "/api/v3/order",
            symbol=position["symbol"],
            side="SELL",
            type="MARKET",
            quantity=position["qty"],
            newOrderRespType="FULL",
        )
        price = avg_price(order)
        return Exit(
            price=price, reason="manual", pnl=(price - position["entry_price"]) * position["qty"]
        )

    def move_stop(self, position: dict, stop: float) -> dict:
        self._cancel_list(position["symbol"], json.loads(position["exchange"])["list"])
        return self._oco(position["symbol"], position["qty"], stop, position["take_profit"])
