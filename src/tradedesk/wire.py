"""Headlines for the dashboard's news panel: crypto, markets, world and politics, newest first.
Separate from news.py, which builds the agents' input and only keeps crypto and macro stories."""

import calendar
import html
import re
import time
from concurrent.futures import ThreadPoolExecutor

import feedparser
import httpx

FEEDS: dict[str, dict[str, str]] = {
    "crypto": {
        "CoinDesk": "https://www.coindesk.com/arc/outboundfeeds/rss/",
        "Cointelegraph": "https://cointelegraph.com/rss",
        "Decrypt": "https://decrypt.co/feed",
        "The Block": "https://www.theblock.co/rss.xml",
    },
    "markets": {
        "CNBC": "https://www.cnbc.com/id/100003114/device/rss/rss.html",
        "CNBC Economy": "https://www.cnbc.com/id/10000664/device/rss/rss.html",
        "MarketWatch": "https://feeds.content.dowjones.io/public/rss/mw_topstories",
        "NYT Business": "https://rss.nytimes.com/services/xml/rss/nyt/Business.xml",
        "BBC Business": "https://feeds.bbci.co.uk/news/business/rss.xml",
    },
    "world": {
        "BBC World": "https://feeds.bbci.co.uk/news/world/rss.xml",
        "Guardian": "https://www.theguardian.com/world/rss",
        "Al Jazeera": "https://www.aljazeera.com/xml/rss/all.xml",
    },
    "politics": {
        "Politico": "https://rss.politico.com/politics-news.xml",
        "NYT Politics": "https://rss.nytimes.com/services/xml/rss/nyt/Politics.xml",
    },
}

_cache: dict[str, tuple[float, list[dict]]] = {}
IMG = re.compile(r"<img[^>]+src=[\"']([^\"']+)", re.I)
TAGS = re.compile(r"<[^>]+>")


def image(entry) -> str | None:
    """The story's picture from media tags, an enclosure or the first image in the summary."""
    for key in ("media_content", "media_thumbnail"):
        for m in entry.get(key) or []:
            url = m.get("url", "")
            if url.startswith("http") and not url.endswith(".mp4"):
                return url
    for link in entry.get("links") or []:
        if link.get("rel") == "enclosure" and str(link.get("type", "")).startswith("image"):
            return link.get("href")
    hit = IMG.search(entry.get("summary", "") or "")
    return hit.group(1) if hit and hit.group(1).startswith("http") else None


def summary(entry) -> str:
    text = html.unescape(TAGS.sub(" ", entry.get("summary", "") or ""))
    text = " ".join(text.split())
    return text[:240].rsplit(" ", 1)[0] + "…" if len(text) > 240 else text


def _one(category: str, source: str, url: str) -> list[dict]:
    try:
        res = httpx.get(
            url, timeout=8, follow_redirects=True, headers={"User-Agent": "tradedesk/0.1"}
        )
        parsed = feedparser.parse(res.content)
    except Exception:
        return []
    out = []
    for e in parsed.entries[:30]:
        stamp = e.get("published_parsed") or e.get("updated_parsed")
        link = e.get("link", "")
        if not stamp or not e.get("title") or not link.startswith("http"):
            continue
        out.append(
            {
                "title": e.title.strip(),
                "link": link,
                "source": source,
                "category": category,
                "ts": calendar.timegm(stamp),
                "image": image(e),
                "summary": summary(e),
            }
        )
    return out


def headlines(max_age_hours: int = 48, ttl: int = 300) -> list[dict]:
    hit = _cache.get("all")
    if hit and time.time() - hit[0] < ttl:
        return hit[1]
    jobs = [(c, s, u) for c, feeds in FEEDS.items() for s, u in feeds.items()]
    with ThreadPoolExecutor(max_workers=8) as pool:
        items = [h for batch in pool.map(lambda j: _one(*j), jobs) for h in batch]
    cutoff = time.time() - max_age_hours * 3600
    seen, out = set(), []
    for h in sorted(items, key=lambda h: h["ts"], reverse=True):
        key = h["title"].lower()[:80]
        if h["ts"] < cutoff or key in seen:
            continue
        seen.add(key)
        out.append(h)
    _cache["all"] = (time.time(), out)
    return out
