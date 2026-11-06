"""Daily, weekly and monthly moves for indexes, sectors, big stocks, commodities, rates and
coins, from Yahoo Finance's public chart endpoint. Watch only, for the overview heatmap."""

import time
from concurrent.futures import ThreadPoolExecutor

import httpx

URL = "https://query1.finance.yahoo.com/v7/finance/spark"
# Yahoo turns away clients without a browser user agent
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15"}
TTL = 300
DAY = 86_400
HORIZONS = {"1d": 1, "1w": 7, "1m": 30}

# group, then (Yahoo symbol, label, sector)
GROUPS: dict[str, list[tuple[str, str, str]]] = {
    "Indexes": [
        ("^GSPC", "S&P 500", "US"),
        ("^NDX", "Nasdaq 100", "US"),
        ("^DJI", "Dow Jones", "US"),
        ("^RUT", "Russell 2000", "US"),
        ("^SSMI", "SMI", "Switzerland"),
        ("^STOXX50E", "Euro Stoxx 50", "Europe"),
        ("^GDAXI", "DAX", "Europe"),
        ("^FTSE", "FTSE 100", "Europe"),
        ("^N225", "Nikkei 225", "Asia"),
        ("^HSI", "Hang Seng", "Asia"),
    ],
    "US sectors": [
        ("XLK", "Technology", "sector"),
        ("XLC", "Communication", "sector"),
        ("XLY", "Consumer discretionary", "sector"),
        ("XLP", "Consumer staples", "sector"),
        ("XLV", "Health care", "sector"),
        ("XLF", "Financials", "sector"),
        ("XLI", "Industrials", "sector"),
        ("XLE", "Energy", "sector"),
        ("XLB", "Materials", "sector"),
        ("XLU", "Utilities", "sector"),
        ("XLRE", "Real estate", "sector"),
        ("SMH", "Semiconductors", "industry"),
        ("IGV", "Software", "industry"),
        ("XBI", "Biotech", "industry"),
        ("ITA", "Aerospace and defense", "industry"),
        ("KRE", "Regional banks", "industry"),
        ("XHB", "Homebuilders", "industry"),
        ("JETS", "Airlines", "industry"),
        ("GDX", "Gold miners", "industry"),
        ("URA", "Uranium", "industry"),
    ],
    "US stocks": [
        ("NVDA", "Nvidia", "Technology"),
        ("AAPL", "Apple", "Technology"),
        ("MSFT", "Microsoft", "Technology"),
        ("GOOGL", "Alphabet", "Communication"),
        ("AMZN", "Amazon", "Consumer"),
        ("META", "Meta", "Communication"),
        ("AVGO", "Broadcom", "Technology"),
        ("TSLA", "Tesla", "Consumer"),
        ("BRK-B", "Berkshire", "Financials"),
        ("JPM", "JPMorgan", "Financials"),
        ("LLY", "Eli Lilly", "Health care"),
        ("V", "Visa", "Financials"),
        ("WMT", "Walmart", "Consumer"),
        ("XOM", "Exxon", "Energy"),
        ("UNH", "UnitedHealth", "Health care"),
        ("COST", "Costco", "Consumer"),
        ("NFLX", "Netflix", "Communication"),
        ("CAT", "Caterpillar", "Industrials"),
        ("COIN", "Coinbase", "Crypto"),
        ("MSTR", "Strategy", "Crypto"),
    ],
    "Swiss stocks": [
        ("NESN.SW", "Nestlé", "Consumer"),
        ("NOVN.SW", "Novartis", "Health care"),
        ("ROG.SW", "Roche", "Health care"),
        ("UBSG.SW", "UBS", "Financials"),
        ("ZURN.SW", "Zurich Insurance", "Financials"),
        ("ABBN.SW", "ABB", "Industrials"),
        ("CFR.SW", "Richemont", "Consumer"),
        ("SIKA.SW", "Sika", "Materials"),
        ("LONN.SW", "Lonza", "Health care"),
        ("SCHP.SW", "Schindler", "Industrials"),
        ("LUKN.SW", "Luzerner KB", "Financials"),
    ],
    "Commodities and rates": [
        ("GC=F", "Gold", "metal"),
        ("SI=F", "Silver", "metal"),
        ("HG=F", "Copper", "metal"),
        ("CL=F", "Oil (WTI)", "energy"),
        ("NG=F", "Natural gas", "energy"),
        ("DX-Y.NYB", "US dollar index", "fx"),
        ("USDCHF=X", "USD/CHF", "fx"),
        ("EURCHF=X", "EUR/CHF", "fx"),
        ("^TNX", "US 10Y yield", "rates"),
    ],
    "Coins": [
        ("BTC-USD", "Bitcoin", "crypto"),
        ("ETH-USD", "Ethereum", "crypto"),
        ("SOL-USD", "Solana", "crypto"),
        ("BNB-USD", "BNB", "crypto"),
        ("XRP-USD", "XRP", "crypto"),
        ("DOGE-USD", "Dogecoin", "crypto"),
        ("ADA-USD", "Cardano", "crypto"),
        ("TRX-USD", "Tron", "crypto"),
        ("AVAX-USD", "Avalanche", "crypto"),
        ("LINK-USD", "Chainlink", "crypto"),
    ],
}

QUOTE = "https://query1.finance.yahoo.com/v7/finance/quote"
CAPS_TTL = 6 * 3600

_cache: tuple[float, dict] | None = None
_caps: tuple[float, dict[str, float]] | None = None


def caps(symbols: list[str]) -> dict[str, float]:
    """Market cap, or fund assets for ETFs, so the heatmap can size its tiles. Yahoo's quote
    endpoint wants a session cookie and a crumb; empty if it refuses, and tiles size evenly."""
    global _caps
    if _caps and time.time() - _caps[0] < CAPS_TTL:
        return _caps[1]
    out: dict[str, float] = {}
    try:
        with httpx.Client(headers=UA, timeout=15, follow_redirects=True) as c:
            c.get("https://fc.yahoo.com")
            crumb = c.get("https://query1.finance.yahoo.com/v1/test/getcrumb").text.strip()
            for i in range(0, len(symbols), 50):
                r = c.get(QUOTE, params={"symbols": ",".join(symbols[i : i + 50]), "crumb": crumb})
                r.raise_for_status()
                for q in (r.json().get("quoteResponse") or {}).get("result") or []:
                    size = q.get("marketCap") or q.get("netAssets") or q.get("totalAssets")
                    if size:
                        out[q["symbol"]] = float(size)
    except (httpx.HTTPError, ValueError):
        pass
    if out:
        _caps = (time.time(), out)
    return out


def changes(timestamps: list[int], closes: list, price: float) -> dict[str, float | None]:
    """Move from the last close at least N days before the latest bar."""
    bars = [(t, c) for t, c in zip(timestamps, closes, strict=False) if c is not None]
    out: dict[str, float | None] = {}
    if not bars or not price:
        return dict.fromkeys(HORIZONS)
    latest = bars[-1][0]
    for name, days in HORIZONS.items():
        before = [c for t, c in bars if t <= latest - days * DAY + DAY // 2]
        out[name] = (price / before[-1] - 1) * 100 if before else None
    return out


def parse(payload: dict) -> dict[str, dict]:
    out = {}
    for row in (payload.get("spark") or {}).get("result") or []:
        resp = (row.get("response") or [{}])[0]
        meta = resp.get("meta") or {}
        price = meta.get("regularMarketPrice")
        quote = ((resp.get("indicators") or {}).get("quote") or [{}])[0]
        if price is None:
            continue
        out[row["symbol"]] = {
            "price": price,
            "currency": meta.get("currency"),
            **changes(resp.get("timestamp") or [], quote.get("close") or [], price),
        }
    return out


def _fetch(symbols: list[str]) -> dict[str, dict]:
    r = httpx.get(
        URL,
        params={"symbols": ",".join(symbols), "range": "3mo", "interval": "1d"},
        headers=UA,
        timeout=15,
    )
    r.raise_for_status()
    return parse(r.json())


def board() -> dict:
    global _cache
    if _cache and time.time() - _cache[0] < TTL:
        return _cache[1]
    symbols = [s for rows in GROUPS.values() for s, _, _ in rows]
    chunks = [symbols[i : i + 20] for i in range(0, len(symbols), 20)]
    quotes: dict[str, dict] = {}
    with ThreadPoolExecutor(len(chunks)) as pool:
        for part in pool.map(_safe, chunks):
            quotes.update(part)
    if not quotes:
        if _cache:
            return _cache[1]
        raise RuntimeError("Yahoo Finance did not answer")
    sizes = caps(symbols)
    out = {
        "groups": [
            {
                "name": group,
                "tiles": [
                    {"symbol": s, "name": label, "sector": sector, "cap": sizes.get(s), **quotes[s]}
                    for s, label, sector in rows
                    if s in quotes
                ],
            }
            for group, rows in GROUPS.items()
        ],
        "as_of": int(time.time()),
    }
    _cache = (time.time(), out)
    return out


def _safe(symbols: list[str]) -> dict[str, dict]:
    try:
        return _fetch(symbols)
    except (httpx.HTTPError, ValueError):
        return {}
