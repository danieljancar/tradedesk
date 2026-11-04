from dataclasses import dataclass
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal
from functools import cached_property

from tradedesk.binance.client import Client
from tradedesk.config import Market
from tradedesk.indicators import Candle


@dataclass(frozen=True)
class SymbolRules:
    tick: float
    step: float
    min_qty: float
    min_notional: float

    def price(self, value: float) -> float:
        return round_to(value, self.tick)

    def qty(self, value: float) -> float:
        return floor_to(value, self.step)


def _snap(value: float, step: float, rounding: str) -> float:
    s = Decimal(str(step)).normalize()
    units = (Decimal(str(value)) / s).quantize(Decimal(1), rounding=rounding)
    return float(units * s)


def floor_to(value: float, step: float) -> float:
    return _snap(value, step, ROUND_DOWN)


def round_to(value: float, step: float) -> float:
    return _snap(value, step, ROUND_HALF_UP)


class MarketData:
    def __init__(self, spot: Client, futures: Client, market: Market):
        self.spot = spot
        self.futures = futures
        self.market = market

    @property
    def trading(self) -> Client:
        return self.spot if self.market is Market.SPOT else self.futures

    def klines(
        self, symbol: str, interval: str, limit: int = 200, start_ms: int | None = None
    ) -> list[Candle]:
        path = "/api/v3/klines" if self.market is Market.SPOT else "/fapi/v1/klines"
        rows = self.trading.public(
            path, symbol=symbol, interval=interval, limit=limit, startTime=start_ms
        )
        return [Candle.from_binance(r) for r in rows]

    def price(self, symbol: str) -> float:
        path = "/api/v3/ticker/price" if self.market is Market.SPOT else "/fapi/v2/ticker/price"
        return float(self.trading.public(path, symbol=symbol)["price"])

    def tickers(self) -> list[dict]:
        """24h stats for every spot pair."""
        return self.spot.public("/api/v3/ticker/24hr")

    def spot_symbols(self) -> list[dict]:
        return self.spot.public("/api/v3/exchangeInfo")["symbols"]

    def derivatives(self, symbol: str) -> dict | None:
        try:
            premium = self.futures.public("/fapi/v1/premiumIndex", symbol=symbol)
            oi = self.futures.public(
                "/futures/data/openInterestHist", symbol=symbol, period="1d", limit=8
            )
            ratio = self.futures.public(
                "/futures/data/globalLongShortAccountRatio", symbol=symbol, period="1d", limit=2
            )
        except Exception:
            return None
        oi_values = [float(r["sumOpenInterestValue"]) for r in oi]
        return {
            "funding_pct": float(premium["lastFundingRate"]) * 100,
            "mark": float(premium["markPrice"]),
            "oi_usd": oi_values[-1] if oi_values else None,
            "oi_change_7d_pct": (oi_values[-1] / oi_values[0] - 1) * 100
            if len(oi_values) > 1
            else None,
            "long_short_ratio": float(ratio[-1]["longShortRatio"]) if ratio else None,
        }

    @cached_property
    def _exchange_info(self) -> dict:
        path = "/api/v3/exchangeInfo" if self.market is Market.SPOT else "/fapi/v1/exchangeInfo"
        info = self.trading.public(path)
        return {s["symbol"]: s for s in info["symbols"]}

    def rules(self, symbol: str) -> SymbolRules:
        filters = {f["filterType"]: f for f in self._exchange_info[symbol]["filters"]}
        lot = filters.get("MARKET_LOT_SIZE") or filters["LOT_SIZE"]
        notional = filters.get("NOTIONAL") or filters.get("MIN_NOTIONAL") or {}
        min_notional = notional.get("minNotional") or notional.get("notional") or 0
        return SymbolRules(
            tick=float(filters["PRICE_FILTER"]["tickSize"]),
            step=max(float(filters["LOT_SIZE"]["stepSize"]), float(lot["stepSize"])),
            min_qty=float(filters["LOT_SIZE"]["minQty"]),
            min_notional=float(min_notional),
        )
