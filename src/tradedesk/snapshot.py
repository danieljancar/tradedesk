from datetime import UTC, datetime

import httpx

from tradedesk.binance.market import MarketData
from tradedesk.config import Settings
from tradedesk.indicators import Candle, atr, ema, macd_hist, pct, rsi, swing_levels


def num(x: float | None, digits: int = 4) -> str:
    if x is None:
        return "n/a"
    if abs(x) >= 1000:
        return f"{x:,.0f}"
    if abs(x) >= 1:
        return f"{x:.2f}"
    return f"{x:.{digits}g}"


def frame_line(name: str, candles: list[Candle]) -> str:
    closes = [c.close for c in candles]
    price = closes[-1]
    parts = []
    for p in (20, 50, 200):
        series = ema(closes, p)
        if series:
            parts.append(f"ema{p} {num(series[-1])}")
    r, a, m = rsi(closes), atr(candles), macd_hist(closes)
    vol_avg = sum(c.volume for c in candles[-21:-1]) / 20
    vol = candles[-1].volume / vol_avg if vol_avg else 0
    parts += [
        f"rsi {r:.0f}" if r is not None else "rsi n/a",
        f"macd_h {num(m)}",
        f"atr {num(a)} ({a / price * 100:.1f}%)" if a else "atr n/a",
        f"vol/avg20 {vol:.1f}",
    ]
    return f"{name}: " + " | ".join(parts)


def asset_block(md: MarketData, symbol: str) -> tuple[str, dict]:
    daily = md.klines(symbol, "1d", 260)
    four = md.klines(symbol, "4h", 200)
    weekly = md.klines(symbol, "1w", 80)
    price = four[-1].close
    closes = [c.close for c in daily]

    def change(days: int) -> str:
        return f"{pct(closes[-days - 1], price):+.1f}%" if len(closes) > days else "n/a"

    sup, res = swing_levels(daily[-120:])
    sup4, res4 = swing_levels(four[-120:])
    recent = four[-30:]
    lines = [
        f"## {symbol} price {num(price)} | 24h {change(1)} 7d {change(7)} 30d {change(30)} "
        f"90d {change(90)}",
        frame_line("4h", four),
        frame_line("1d", daily),
        frame_line("1w", weekly),
        f"levels 1d: support {', '.join(map(num, sup)) or 'none'} | "
        f"resistance {', '.join(map(num, res)) or 'none'}",
        f"levels 4h: support {', '.join(map(num, sup4)) or 'none'} | "
        f"resistance {', '.join(map(num, res4)) or 'none'}",
        f"4h range last 5d: {num(min(c.low for c in recent))} to "
        f"{num(max(c.high for c in recent))}",
        "daily closes (old to new): " + " ".join(num(c) for c in closes[-14:]),
    ]
    deriv = md.derivatives(symbol)
    if deriv:
        lines.append(
            f"derivatives: funding {deriv['funding_pct']:+.4f}%/8h | OI {num(deriv['oi_usd'])} USD "
            f"(7d {num(deriv['oi_change_7d_pct'])}%) | long/short accounts "
            f"{num(deriv['long_short_ratio'])}"
        )
    else:
        lines.append("derivatives: not available (not a measured zero)")
    facts = {
        "price": price,
        "atr_4h": atr(four),
        "atr_1d": atr(daily),
    }
    return "\n".join(lines), facts


def sentiment() -> str:
    try:
        data = httpx.get("https://api.alternative.me/fng/", params={"limit": 7}, timeout=10).json()
        values = [f"{d['value']} ({d['value_classification']})" for d in data["data"]]
        fng = "fear & greed (today first): " + ", ".join(values)
    except Exception:
        fng = "fear & greed: not available"
    try:
        g = httpx.get("https://api.coingecko.com/api/v3/global", timeout=10).json()["data"]
        mc = g["market_cap_percentage"]
        glob = (
            f"total market cap {num(g['total_market_cap']['usd'])} USD "
            f"(24h {g['market_cap_change_percentage_24h_usd']:+.1f}%) | "
            f"dominance BTC {mc['btc']:.1f}% ETH {mc['eth']:.1f}%"
        )
    except Exception:
        glob = "global market data: not available"
    return f"{fng}\n{glob}"


def build(settings: Settings, md: MarketData) -> tuple[str, dict[str, dict]]:
    stamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    blocks, facts = [f"# Market snapshot {stamp}", sentiment()], {}
    for asset in settings.watchlist:
        symbol = settings.symbol(asset)
        try:
            block, facts[asset] = asset_block(md, symbol)
        except Exception as e:
            block = f"## {symbol}\ndata error: {e}. Do not trade this asset today."
        blocks.append(block)
    return "\n\n".join(blocks) + "\n", facts
