import calendar
import re
import time
from dataclasses import dataclass
from urllib.parse import urlparse

import feedparser
import httpx

NAMES = {
    "BTC": ["bitcoin", "btc"],
    "ETH": ["ethereum", "ether", "eth"],
    "SOL": ["solana", "sol"],
    "BNB": ["bnb", "binance coin"],
    "XRP": ["xrp", "ripple"],
    "ADA": ["cardano", "ada"],
    "DOGE": ["dogecoin", "doge"],
    "AVAX": ["avalanche", "avax"],
    "LINK": ["chainlink", "link"],
    "SUI": ["sui"],
}
MACRO = re.compile(
    r"\b(fed|fomc|powell|rate cut|rate hike|cpi|inflation|jobs report|payrolls|treasury|"
    r"tariff|sec|etf|regulat\w*|stablecoin|recession|dollar)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Headline:
    title: str
    source: str
    published: float

    def line(self) -> str:
        hours = (time.time() - self.published) / 3600
        return f"- [{hours:.0f}h, {self.source}] {self.title}"


def fetch(feeds: list[str], max_age_hours: int = 36) -> list[Headline]:
    cutoff = time.time() - max_age_hours * 3600
    seen, items = set(), []
    for url in feeds:
        try:
            body = httpx.get(url, timeout=10, follow_redirects=True).text
        except httpx.HTTPError:
            continue
        source = urlparse(url).netloc.removeprefix("www.").split(".")[0]
        for entry in feedparser.parse(body).entries:
            stamp = entry.get("published_parsed") or entry.get("updated_parsed")
            if not stamp:
                continue
            published = calendar.timegm(stamp)
            title = re.sub(r"\s+", " ", entry.get("title", "")).strip()
            key = re.sub(r"\W+", "", title.lower())[:60]
            if published < cutoff or not title or key in seen:
                continue
            seen.add(key)
            items.append(Headline(title, source, published))
    return sorted(items, key=lambda h: h.published, reverse=True)


def mentions(headline: Headline, asset: str) -> bool:
    words = NAMES.get(asset, [asset.lower()])
    return any(re.search(rf"\b{re.escape(w)}\b", headline.title, re.IGNORECASE) for w in words)


def build(feeds: list[str], watchlist: list[str], limit: int = 12) -> str:
    items = fetch(feeds)
    if not items:
        return "# News\nNo headlines could be fetched. Use web search for news today.\n"
    out = [f"# News, last 36h ({len(items)} unique headlines)"]
    for asset in watchlist:
        hits = [h for h in items if mentions(h, asset)][:limit]
        out.append(f"## {asset}")
        out += [h.line() for h in hits] or ["- no headlines mention it"]
    macro = [h for h in items if MACRO.search(h.title)][:limit]
    out.append("## Macro and regulation")
    out += [h.line() for h in macro] or ["- none"]
    tagged = {h for a in watchlist for h in items if mentions(h, a)} | set(macro)
    rest = [h for h in items if h not in tagged][:limit]
    out.append("## Other market headlines")
    out += [h.line() for h in rest] or ["- none"]
    return "\n".join(out) + "\n"
