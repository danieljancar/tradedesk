"""Which assets the desk looks at today: the watchlist, fixed extras, gold and the top movers
of the whole spot market by momentum and volume."""

import json
from collections.abc import Iterable
from pathlib import Path

from tradedesk.binance.market import MarketData
from tradedesk.config import Settings
from tradedesk.indicators import atr

STABLES = {
    "USDT",
    "USDC",
    "FDUSD",
    "TUSD",
    "DAI",
    "USDP",
    "BUSD",
    "EUR",
    "TRY",
    "BRL",
    "AEUR",
    "USD1",
    "PYUSD",
    "XUSD",
}
LEVERAGED = ("UP", "DOWN", "BULL", "BEAR")
GOLD = {"PAXG", "XAUT"}
CANDIDATES = 30
WEIGHTS = {"rel_btc_7d": 0.5, "vol_surge": 0.3, "atr_pct": 0.2}
FIELDS = (
    "score",
    "price",
    "change_24h",
    "change_7d",
    "rel_btc_7d",
    "vol_surge",
    "atr_pct",
    "quote_volume",
    "reason",
)


def asset_class(asset: str) -> str:
    return "gold" if asset.upper() in GOLD else "crypto"


def entry(asset: str, source: str, **values) -> dict:
    asset = asset.upper()
    return {"asset": asset, "asset_class": asset_class(asset), "source": source} | {
        k: values.get(k) for k in FIELDS
    }


def leveraged(base: str, bases: set[str]) -> bool:
    return any(
        base.endswith(s) and len(base) - len(s) >= 2 and base[: -len(s)] in bases for s in LEVERAGED
    )


def candidates(
    settings: Settings, tickers: list[dict], symbols: list[dict], skip: set[str] = frozenset()
) -> list[dict]:
    """Liquid, trading pairs in the quote currency, without stablecoins, fiat, leveraged
    tokens or tagged assets, sorted by 24h quote volume."""
    quote = settings.quote.upper()
    excluded = STABLES | {a.upper() for a in settings.universe.exclude} | {quote} | skip
    pairs = {
        s["symbol"]: s["baseAsset"]
        for s in symbols
        if s.get("quoteAsset") == quote and s.get("status") == "TRADING"
    }
    bases = set(pairs.values())
    out = []
    for t in tickers:
        base = pairs.get(t["symbol"])
        if not base or base in excluded or leveraged(base, bases):
            continue
        volume = float(t["quoteVolume"])
        if volume < settings.universe.min_quote_volume:
            continue
        out.append(
            {
                "asset": base,
                "symbol": t["symbol"],
                "price": float(t["lastPrice"]),
                "change_24h": float(t["priceChangePercent"]),
                "quote_volume": volume,
            }
        )
    return sorted(out, key=lambda c: c["quote_volume"], reverse=True)


def change_7d(closes: list[float]) -> float | None:
    return (closes[-1] / closes[-8] - 1) * 100 if len(closes) >= 8 and closes[-8] else None


def measure(md: MarketData, c: dict, btc_7d: float) -> dict | None:
    daily = md.klines(c["symbol"], "1d", 30)
    closes = [k.close for k in daily]
    move = change_7d(closes)
    if move is None:
        return None
    week = [k.volume * k.close for k in daily[-8:-1]]
    avg = sum(week) / len(week) if week else 0
    a = atr(daily)
    return c | {
        "change_7d": round(move, 2),
        "rel_btc_7d": round(move - btc_7d, 2),
        "vol_surge": round(c["quote_volume"] / avg, 2) if avg else 1.0,
        "atr_pct": round(a / closes[-1] * 100, 2) if a and closes[-1] else 0.0,
    }


def ranks(values: list[float]) -> list[float]:
    """Percentile rank of each value, 0 for the smallest and 1 for the largest."""
    if len(values) < 2:
        return [1.0] * len(values)
    order = sorted(values)
    return [order.index(v) / (len(values) - 1) for v in values]


def reason(row: dict, btc_7d: float) -> str:
    move = row["change_7d"]
    word = "up" if move >= 0 else "down"
    return (
        f"{word} {abs(move):.0f}% in 7d vs BTC {btc_7d:+.0f}%, volume "
        f"{row['vol_surge']:.1f}x its weekly average, ATR {row['atr_pct']:.1f}% of price"
    )


def score(rows: list[dict], btc_7d: float) -> list[dict]:
    """Strong moves both ways rank high: distance from BTC counts, not its sign."""
    parts = {
        "rel_btc_7d": ranks([abs(r["rel_btc_7d"]) for r in rows]),
        "vol_surge": ranks([r["vol_surge"] for r in rows]),
        "atr_pct": ranks([r["atr_pct"] for r in rows]),
    }
    out = []
    for i, r in enumerate(rows):
        total = sum(WEIGHTS[k] * parts[k][i] for k in WEIGHTS) * 100
        values = {k: r[k] for k in FIELDS if k in r}
        out.append(
            entry(r["asset"], "scan", **values, score=round(total, 1), reason=reason(r, btc_7d))
        )
    return sorted(out, key=lambda r: r["score"], reverse=True)


def scan(settings: Settings, md: MarketData) -> list[dict]:
    skip = md.tagged(settings.universe.exclude_tags)
    pool = candidates(settings, md.tickers(), md.spot_symbols(), skip)[:CANDIDATES]
    btc = change_7d([k.close for k in md.klines(settings.symbol("BTC"), "1d", 30)]) or 0.0
    rows = []
    for c in pool:
        try:
            row = measure(md, c, btc)
        except Exception:
            continue
        if row:
            rows.append(row)
    return score(rows, btc)[: settings.universe.top]


def assets_for_run(
    settings: Settings, scanned: list[dict], extra: Iterable[str] = ()
) -> list[dict]:
    u = settings.universe
    wanted = [
        *(entry(a, "watchlist") for a in settings.watchlist),
        *(entry(a, "always") for a in u.always),
        *([entry("PAXG", "gold")] if u.include_gold else []),
        *(entry(a, "core") for a in extra),
        *scanned,
    ]
    out: dict[str, dict] = {}
    for item in wanted:
        kept = out.get(item["asset"])
        if kept is None:
            out[item["asset"]] = dict(item)
            continue
        for k in FIELDS:
            if kept[k] is None:
                kept[k] = item.get(k)
    return list(out.values())[: u.max_assets]


def watchlist(settings: Settings) -> list[dict]:
    return [entry(a, "watchlist") for a in settings.watchlist]


def markdown(assets: list[dict]) -> str:
    lines = [f"# Universe today ({len(assets)} assets)"]
    for a in assets:
        why = a["reason"] or f"from the {a['source']} list"
        lines.append(f"- {a['asset']} ({a['source']}, {a['asset_class']}): {why}")
    return "\n".join(lines) + "\n"


def write(run_dir: Path, assets: list[dict]) -> str:
    text = markdown(assets)
    (run_dir / "universe.md").write_text(text)
    (run_dir / "universe.json").write_text(json.dumps(assets, indent=1))
    return text


def read(run_dir: Path) -> list[dict] | None:
    path = run_dir / "universe.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except ValueError:
        return None
