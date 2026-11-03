from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from tradedesk.binance.market import SymbolRules


@dataclass
class Placed:
    open: bool
    refs: dict = field(default_factory=dict)
    fill_price: float | None = None
    qty: float | None = None


@dataclass
class Fill:
    price: float
    qty: float
    at: str
    refs: dict = field(default_factory=dict)


@dataclass
class Exit:
    price: float
    reason: str
    pnl: float | None = None


class Unprotected(RuntimeError):
    """A position is open on the exchange without a working stop."""


def ms(iso: str) -> int:
    return int(datetime.fromisoformat(iso).timestamp() * 1000)


class Broker(Protocol):
    def equity(self) -> float: ...

    def free_quote(self) -> float: ...

    def price(self, symbol: str) -> float: ...

    def rules(self, symbol: str) -> SymbolRules: ...

    def place(self, plan: dict) -> Placed: ...

    def entry_status(self, plan: dict) -> Fill | str | None:
        """Fill when filled, 'cancelled' when the exchange dropped it, None if waiting."""

    def exit_status(self, position: dict) -> Exit | None: ...

    def cancel(self, plan: dict) -> Fill | None:
        """Cancel a resting entry. Returns a Fill when part of it had already filled."""

    def close(self, position: dict) -> Exit: ...

    def move_stop(self, position: dict, stop: float) -> dict: ...
