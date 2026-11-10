"""Binance's own announcements of new listings, so the desk sees a launch before it happens."""

import time

import httpx

URL = "https://www.binance.com/bapi/composite/v1/public/cms/article/list/query"
LINK = "https://www.binance.com/en/support/announcement/detail/"
NEW_LISTINGS = 48
TTL = 600

_cache: tuple[float, list[dict]] | None = None


def recent(days: int = 7) -> list[dict]:
    """Listing announcements of the last days, newest first. Empty if Binance doesn't answer."""
    global _cache
    if _cache and time.time() - _cache[0] < TTL:
        rows = _cache[1]
    else:
        try:
            r = httpx.get(
                URL,
                params={"type": 1, "catalogId": NEW_LISTINGS, "pageNo": 1, "pageSize": 20},
                timeout=10,
            )
            r.raise_for_status()
            articles = r.json()["data"]["catalogs"][0]["articles"]
        except (httpx.HTTPError, ValueError, KeyError, IndexError):
            return _cache[1] if _cache else []
        rows = [
            {"title": a["title"], "ts": a["releaseDate"] / 1000, "url": LINK + a["code"]}
            for a in articles
        ]
        _cache = (time.time(), rows)
    cutoff = time.time() - days * 86_400
    return [r for r in rows if r["ts"] >= cutoff]
