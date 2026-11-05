"""What people are searching for right now, from CoinGecko's free trending list. Watch only:
the desk never trades from this list, it only shows which of the names Binance lists."""

import time

import httpx

URL = "https://api.coingecko.com/api/v3/search/trending"
UA = {"User-Agent": "tradedesk/0.1 (+https://github.com/danieljancar/tradedesk)"}
TTL = 600
_cache: tuple[float, list[dict]] | None = None


def parse(payload: dict, listed: set[str]) -> list[dict]:
    out = []
    for row in payload.get("coins", []):
        item = row.get("item", {})
        data = item.get("data") or {}
        symbol = str(item.get("symbol", "")).upper()
        change = (data.get("price_change_percentage_24h") or {}).get("usd")
        out.append(
            {
                "symbol": symbol,
                "name": item.get("name", symbol),
                "rank": item.get("market_cap_rank"),
                "price": _num(data.get("price")),
                "change_24h": _num(change),
                "volume": _money(data.get("total_volume")),
                "on_binance": symbol in listed,
                "url": f"https://www.coingecko.com/en/coins/{item.get('id', '')}",
            }
        )
    return out


def coins(listed: set[str]) -> list[dict] | None:
    global _cache
    if _cache and time.monotonic() - _cache[0] < TTL:
        return _cache[1]
    try:
        r = httpx.get(URL, headers=UA, timeout=10)
        r.raise_for_status()
        rows = parse(r.json(), listed)
    except Exception:
        return _cache[1] if _cache else None
    _cache = (time.monotonic(), rows)
    return rows


def _num(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _money(v) -> float | None:
    if isinstance(v, str):
        v = v.replace("$", "").replace(",", "")
    return _num(v)
