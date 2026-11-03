import hashlib
import hmac
import time
from typing import Any
from urllib.parse import urlencode

import httpx

from tradedesk.config import Market, Mode, Settings

URLS = {
    (Market.SPOT, Mode.LIVE): "https://api.binance.com",
    (Market.SPOT, Mode.PAPER): "https://api.binance.com",
    (Market.SPOT, Mode.TESTNET): "https://testnet.binance.vision",
    (Market.FUTURES, Mode.LIVE): "https://fapi.binance.com",
    (Market.FUTURES, Mode.PAPER): "https://fapi.binance.com",
    (Market.FUTURES, Mode.TESTNET): "https://testnet.binancefuture.com",
}


class BinanceError(RuntimeError):
    def __init__(self, status: int, code: int | None, message: str):
        super().__init__(f"Binance {status} {code}: {message}")
        self.code = code


def base_url(settings: Settings, market: Market) -> str:
    override = settings.spot_url if market is Market.SPOT else settings.futures_url
    return override or URLS[(market, settings.mode)]


def fmt(value: Any) -> str:
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, float):
        return f"{value:.10f}".rstrip("0").rstrip(".")
    return str(value)


class Client:
    def __init__(self, base: str, key: str = "", secret: str = "", timeout: float = 15):
        self.key = key
        self.secret = secret.encode()
        self.http = httpx.Client(base_url=base, timeout=timeout)

    def public(self, path: str, **params: Any) -> Any:
        return self._send("GET", path, params, signed=False)

    def signed(self, method: str, path: str, **params: Any) -> Any:
        return self._send(method, path, params, signed=True)

    def _send(self, method: str, path: str, params: dict, signed: bool) -> Any:
        clean = {k: fmt(v) for k, v in params.items() if v is not None}
        headers = {}
        if signed:
            clean["timestamp"] = str(int(time.time() * 1000))
            clean.setdefault("recvWindow", "5000")
            query = urlencode(clean)
            sig = hmac.new(self.secret, query.encode(), hashlib.sha256).hexdigest()
            clean["signature"] = sig
            headers["X-MBX-APIKEY"] = self.key
        response = self.http.request(method, path, params=clean, headers=headers)
        if response.status_code >= 400:
            try:
                data = response.json()
                raise BinanceError(response.status_code, data.get("code"), data.get("msg", ""))
            except ValueError:
                raise BinanceError(response.status_code, None, response.text[:200]) from None
        return response.json()
