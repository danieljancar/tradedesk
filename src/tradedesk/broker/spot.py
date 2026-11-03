import json

import httpx

from tradedesk.binance.client import BinanceError, Client
from tradedesk.binance.market import MarketData, SymbolRules
from tradedesk.broker.base import Exit, Fill, Placed, Unprotected
from tradedesk.config import Settings
from tradedesk.db import now
from tradedesk.risk import SPOT_FEE_BUFFER as FEE_BUFFER

DEAD = ("CANCELED", "EXPIRED", "REJECTED", "EXPIRED_IN_MATCH")


def avg_price(order: dict) -> float:
    qty = float(order["executedQty"])
    return float(order["cummulativeQuoteQty"]) / qty if qty else 0.0


def client_id(plan: dict) -> str:
    return f"desk-{plan['id']}"


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

    def _order(self, symbol: str, order_id: int) -> dict:
        return self.client.signed("GET", "/api/v3/order", symbol=symbol, orderId=order_id)

    def _sell(self, symbol: str, qty: float) -> dict:
        return self.client.signed(
            "POST",
            "/api/v3/order",
            symbol=symbol,
            side="SELL",
            type="MARKET",
            quantity=qty,
            newOrderRespType="FULL",
        )

    @staticmethod
    def _legs(report: dict) -> dict:
        legs = {}
        for o in report.get("orderReports", []):
            kind = {"LIMIT": "entry", "LIMIT_MAKER": "target", "STOP_LOSS": "stop"}.get(o["type"])
            if kind:
                legs[kind] = o["orderId"]
        return legs

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

    def _protect(self, symbol: str, qty: float, stop: float, target: float) -> dict:
        """Stop and target for coins already held. Sells them if the OCO doesn't go through."""
        try:
            return self._oco(symbol, qty, stop, target)
        except Exception:
            self._sell(symbol, qty)
            raise

    def _resolve_legs(self, symbol: str, listing: dict) -> dict:
        legs = {}
        for o in listing["orders"]:
            legs |= self._legs({"orderReports": [self._order(symbol, o["orderId"])]})
        return {"list": listing["orderListId"], **legs}

    def place(self, plan: dict) -> Placed:
        symbol = plan["symbol"]
        if plan["entry_type"] == "market":
            try:
                order = self.client.signed(
                    "POST",
                    "/api/v3/order",
                    symbol=symbol,
                    side="BUY",
                    type="MARKET",
                    quantity=plan["qty"],
                    newClientOrderId=client_id(plan),
                    newOrderRespType="FULL",
                )
            except httpx.HTTPError:
                order = self.client.signed(
                    "GET", "/api/v3/order", symbol=symbol, origClientOrderId=client_id(plan)
                )
            filled = float(order["executedQty"])
            if not filled:
                raise RuntimeError(f"market buy for plan {plan['id']} did not fill")
            exit_qty = self._exit_qty(symbol, filled)
            refs = self._protect(symbol, exit_qty, plan["stop"], plan["take_profit"])
            return Placed(open=True, fill_price=avg_price(order), qty=exit_qty, refs=refs)
        params = dict(
            symbol=symbol,
            listClientOrderId=client_id(plan),
            workingType="LIMIT",
            workingSide="BUY",
            workingPrice=plan["entry"],
            workingQuantity=plan["qty"],
            workingTimeInForce="GTC",
            pendingSide="SELL",
            pendingQuantity=self._exit_qty(symbol, plan["qty"]),
            pendingAboveType="LIMIT_MAKER",
            pendingAbovePrice=plan["take_profit"],
            pendingBelowType="STOP_LOSS",
            pendingBelowStopPrice=plan["stop"],
            newOrderRespType="RESULT",
        )
        try:
            report = self.client.signed("POST", "/api/v3/orderList/otoco", **params)
        except httpx.HTTPError:
            listing = self.client.signed(
                "GET", "/api/v3/orderList", origClientOrderId=client_id(plan)
            )
            return Placed(open=False, refs=self._resolve_legs(symbol, listing))
        refs = {"list": report["orderListId"], **self._legs(report)}
        if not {"entry", "stop", "target"} <= refs.keys():
            listing = self.client.signed(
                "GET", "/api/v3/orderList", orderListId=report["orderListId"]
            )
            refs = self._resolve_legs(symbol, listing)
        return Placed(open=False, refs=refs)

    def entry_status(self, plan: dict) -> Fill | str | None:
        refs = json.loads(plan["exchange"])
        order = self._order(plan["symbol"], refs["entry"])
        if order["status"] == "FILLED":
            qty = self._exit_qty(plan["symbol"], float(order["executedQty"]))
            return Fill(price=avg_price(order), qty=qty, at=now(), refs=refs)
        if order["status"] in DEAD:
            return self._salvage(plan, order) or "cancelled"
        return None

    def _salvage(self, plan: dict, order: dict) -> Fill | None:
        """Protect whatever part of a cancelled entry did fill."""
        filled = float(order["executedQty"])
        if not filled:
            return None
        rules = self.rules(plan["symbol"])
        qty = self._exit_qty(plan["symbol"], filled)
        if qty < rules.min_qty or qty * plan["stop"] < rules.min_notional:
            return None
        refs = self._protect(plan["symbol"], qty, plan["stop"], plan["take_profit"])
        return Fill(price=avg_price(order), qty=qty, at=now(), refs=refs)

    def cancel(self, plan: dict) -> Fill | None:
        refs = json.loads(plan["exchange"])
        self._cancel_list(plan["symbol"], refs["list"])
        return self._salvage(plan, self._order(plan["symbol"], refs["entry"]))

    def exit_status(self, position: dict) -> Exit | None:
        refs = json.loads(position["exchange"])
        legs = {leg: self._order(position["symbol"], refs[leg]) for leg in ("stop", "target")}
        for leg, order in legs.items():
            if order["status"] == "FILLED":
                price = avg_price(order)
                pnl = (price - position["entry_price"]) * float(order["executedQty"])
                return Exit(price=price, reason=leg, pnl=pnl)
        statuses = {o["status"] for o in legs.values()}
        if "PARTIALLY_FILLED" in statuses or statuses <= set(DEAD):
            raise Unprotected(f"{position['symbol']} position {position['id']} has no full stop")
        return None

    def _cancel_list(self, symbol: str, list_id: int) -> None:
        try:
            self.client.signed("DELETE", "/api/v3/orderList", symbol=symbol, orderListId=list_id)
        except BinanceError as e:
            if e.code != -2011:
                raise

    def close(self, position: dict) -> Exit:
        try:
            done = self.exit_status(position)
        except Unprotected:
            done = None
        if done:
            return done
        self._cancel_list(position["symbol"], json.loads(position["exchange"])["list"])
        price = avg_price(self._sell(position["symbol"], position["qty"]))
        return Exit(
            price=price, reason="manual", pnl=(price - position["entry_price"]) * position["qty"]
        )

    def move_stop(self, position: dict, stop: float) -> dict:
        symbol, qty, target = position["symbol"], position["qty"], position["take_profit"]
        self._cancel_list(symbol, json.loads(position["exchange"])["list"])
        try:
            return self._oco(symbol, qty, stop, target)
        except Exception:
            self._protect(symbol, qty, position["stop"], target)
            raise
