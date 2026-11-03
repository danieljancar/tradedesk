"""The things that move crypto: stocks, the dollar, rates, volatility, oil, Fed liquidity,
stablecoin supply, total crypto market and sentiment. Free sources only, cached.

Each driver gets a plain rule for whether it's a tailwind or a headwind for crypto right now.
The rules are deliberately simple and visible; they summarise, they don't predict."""

import csv
import io
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta

import httpx

FRED = "https://fred.stlouisfed.org/graph/fredgraph.csv"
UA = {"User-Agent": "tradedesk/0.1 (+https://github.com/danieljancar/tradedesk)"}

# id, name, group, unit, how to read it for crypto
SERIES = [
    (
        "SP500",
        "S&P 500",
        "Stocks",
        "",
        "Crypto has traded closely with US stocks. Stocks rising helps.",
    ),
    (
        "NASDAQCOM",
        "Nasdaq",
        "Stocks",
        "",
        "Tech stocks are the closest cousin to crypto risk appetite.",
    ),
    (
        "DTWEXBGS",
        "US dollar",
        "Dollar & rates",
        "",
        "A falling dollar usually helps crypto; a rising one drains it.",
    ),
    (
        "DGS10",
        "10Y yield",
        "Dollar & rates",
        "%",
        "Falling long-term rates make risky assets more attractive.",
    ),
    (
        "T10Y2Y",
        "Yield curve",
        "Dollar & rates",
        "%",
        "10Y minus 2Y. Below zero has preceded recessions.",
    ),
    ("VIXCLS", "VIX", "Risk", "", "Stock-market fear gauge. Under 18 calm, over 25 stressed."),
    (
        "DCOILWTICO",
        "Oil (WTI)",
        "Risk",
        "$",
        "Fast-rising oil feeds inflation and keeps rates high.",
    ),
    (
        "WALCL",
        "Fed balance sheet",
        "Liquidity",
        "$bn",
        "Fed adding money (rising) tends to lift crypto; shrinking drains it.",
    ),
]

_cache: dict[str, tuple[float, object]] = {}


def _cached(key: str, ttl: int, fn):
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < ttl:
        return hit[1]
    try:
        value = fn()
    except Exception:
        return hit[1] if hit else None
    _cache[key] = (time.time(), value)
    return value


def fred(series_id: str, days: int = 400) -> list[tuple[str, float]]:
    start = (date.today() - timedelta(days=days)).isoformat()
    res = httpx.get(FRED, params={"id": series_id, "cosd": start}, timeout=15, headers=UA)
    res.raise_for_status()
    rows = list(csv.reader(io.StringIO(res.text)))[1:]
    out = []
    for d, v in rows:
        try:
            out.append((d, float(v)))
        except ValueError:
            continue
    return out


def stablecoins(days: int = 400) -> list[tuple[str, float]]:
    data = httpx.get("https://stablecoins.llama.fi/stablecoincharts/all", timeout=15).json()
    out = []
    for row in data[-days:]:
        d = datetime.fromtimestamp(int(row["date"]), UTC).date().isoformat()
        out.append((d, row["totalCirculatingUSD"]["peggedUSD"] / 1e9))
    return out


def fear_greed(days: int = 120) -> list[tuple[str, float]]:
    data = httpx.get("https://api.alternative.me/fng/", params={"limit": days}, timeout=10).json()
    rows = [
        (datetime.fromtimestamp(int(d["timestamp"]), UTC).date().isoformat(), float(d["value"]))
        for d in data["data"]
    ]
    return sorted(rows)


def crypto_global() -> dict:
    g = httpx.get("https://api.coingecko.com/api/v3/global", timeout=10).json()["data"]
    return {
        "market_cap": g["total_market_cap"]["usd"],
        "volume": g["total_volume"]["usd"],
        "change_24h": g["market_cap_change_percentage_24h_usd"],
        "btc_dominance": g["market_cap_percentage"]["btc"],
        "eth_dominance": g["market_cap_percentage"]["eth"],
    }


def _change(points: list[tuple[str, float]], days: int) -> float | None:
    if not points:
        return None
    last_d = date.fromisoformat(points[-1][0])
    target = last_d - timedelta(days=days)
    past = [v for d, v in points if date.fromisoformat(d) <= target]
    if not past or past[-1] == 0:
        return None
    return (points[-1][1] - past[-1]) / abs(past[-1]) * 100


def _sma(points: list[tuple[str, float]], n: int) -> float | None:
    vals = [v for _, v in points[-n:]]
    return sum(vals) / len(vals) if len(vals) >= n else None


def _verdict(sid: str, points: list[tuple[str, float]]) -> tuple[int, str]:
    """+1 tailwind, -1 headwind, 0 neutral, with a short reason."""
    if not points:
        return 0, "no data"
    last = points[-1][1]
    m1 = _change(points, 30) or 0
    sma50 = _sma(points, 50)
    if sid in ("SP500", "NASDAQCOM"):
        if sma50 and last > sma50 and m1 > 0:
            return 1, f"above its 50-day average, {m1:+.1f}% in a month"
        if sma50 and last < sma50 and m1 < 0:
            return -1, f"below its 50-day average, {m1:+.1f}% in a month"
        return 0, f"{m1:+.1f}% in a month, no clear trend"
    if sid == "DTWEXBGS":
        return (1 if m1 < -0.5 else -1 if m1 > 0.5 else 0), f"{m1:+.1f}% in a month"
    if sid == "DGS10":
        bp = (last - points[-22][1]) * 100 if len(points) > 22 else 0
        return (
            1 if bp < -10 else -1 if bp > 10 else 0
        ), f"{bp:+.0f} bp in a month, now {last:.2f}%"
    if sid == "T10Y2Y":
        return (-1 if last < 0 else 0), f"{last:+.2f}% {'(inverted)' if last < 0 else ''}".strip()
    if sid == "VIXCLS":
        return (1 if last < 18 else -1 if last > 25 else 0), f"{last:.1f}"
    if sid == "DCOILWTICO":
        return (-1 if m1 > 10 else 1 if m1 < -10 else 0), f"{m1:+.1f}% in a month"
    if sid == "WALCL":
        return (1 if m1 > 0.3 else -1 if m1 < -0.3 else 0), f"{m1:+.2f}% in a month"
    if sid == "STABLES":
        return (1 if m1 > 1 else -1 if m1 < -1 else 0), f"{m1:+.1f}% in a month"
    return 0, ""


def _pack(sid, name, group, unit, why, points) -> dict:
    tilt, reason = _verdict(sid, points)
    tail = points[-120:]
    return {
        "id": sid,
        "name": name,
        "group": group,
        "unit": unit,
        "why": why,
        "value": points[-1][1] if points else None,
        "as_of": points[-1][0] if points else None,
        "change_1w": _change(points, 7),
        "change_1m": _change(points, 30),
        "change_3m": _change(points, 91),
        "series": [{"d": d, "v": v} for d, v in tail],
        "tilt": tilt,
        "reason": reason,
    }


def overview() -> dict:
    def build() -> dict:
        with ThreadPoolExecutor(max_workers=8) as pool:
            fred_data = dict(
                zip(
                    [s[0] for s in SERIES],
                    pool.map(lambda s: _safe(fred, s[0]), SERIES),
                    strict=True,
                )
            )
            stables = pool.submit(_safe, stablecoins)
            fng = pool.submit(_safe, fear_greed)
            glob = pool.submit(_safe, crypto_global, default={})
        drivers = []
        for sid, name, group, unit, why in SERIES:
            pts = fred_data.get(sid) or []
            if sid == "WALCL":
                pts = [(d, v / 1000) for d, v in pts]
            drivers.append(_pack(sid, name, group, unit, why, pts))
        drivers.append(
            _pack(
                "STABLES",
                "Stablecoin supply",
                "Liquidity",
                "$bn",
                "Dollars parked on-chain, ready to buy crypto. Growing supply is fresh fuel.",
                stables.result() or [],
            )
        )
        scored = [d for d in drivers if d["value"] is not None]
        score = sum(d["tilt"] for d in scored)
        tail = sum(d["tilt"] > 0 for d in scored)
        head = sum(d["tilt"] < 0 for d in scored)
        regime = "Risk-on" if score >= 2 else "Risk-off" if score <= -2 else "Mixed"
        fg = fng.result() or []
        return {
            "updated": datetime.now(UTC).isoformat(timespec="seconds"),
            "regime": {
                "label": regime,
                "score": score,
                "tailwinds": tail,
                "headwinds": head,
                "total": len(scored),
            },
            "drivers": drivers,
            "crypto": glob.result() or {},
            "fear_greed": [{"d": d, "v": v} for d, v in fg],
        }

    return _cached("overview", 900, build)


def _safe(fn, *args, default=None):
    try:
        return fn(*args)
    except Exception:
        return default
