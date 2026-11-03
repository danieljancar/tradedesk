"""Learning from experience. Every idea, taken or not, is replayed on real 1h candles until it
resolves, and every run remembers what the watchlist did in the 24h and 72h after it. Stats on
top of that carry their sample size; nothing under MIN_SAMPLE examples counts as a lesson."""

import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from tradedesk.binance.market import MarketData
from tradedesk.config import Horizon, Settings
from tradedesk.db import Database, now
from tradedesk.indicators import Candle
from tradedesk.replay import replay

MIN_SAMPLE = 10
HOUR = 3_600_000
RESOLVED = ("target", "stop", "expired", "timeout")
FILLED = ("target", "stop", "timeout")
WINDOWS = {"24h": 24, "72h": 72}
NOT_ENOUGH = "not enough data yet"


def ms(iso: str) -> int:
    return int(datetime.fromisoformat(iso).timestamp() * 1000)


def iso(ms_value: int | None) -> str | None:
    if ms_value is None:
        return None
    return datetime.fromtimestamp(ms_value / 1000, UTC).isoformat(timespec="seconds")


def decision(plan: dict) -> str:
    """taken: approved and sent; passed: cleared the risk check, not taken; rejected: failed it."""
    if plan["status"] == "rejected" and not (plan["reasons"] or "").startswith("exchange:"):
        return "rejected"
    return "passed" if plan["status"] in ("proposed", "cancelled") else "taken"


def context(facts: dict, market: dict) -> dict:
    """The market context keys kept next to every outcome."""
    d1 = (facts.get("frames") or {}).get("1d") or {}
    fng = market.get("fear_greed") or [{}]
    price, ema200 = facts.get("price"), d1.get("ema200")
    return {
        "fear_greed": fng[0].get("value"),
        "btc_dominance": (market.get("dominance") or {}).get("BTC"),
        "funding_pct": (facts.get("derivatives") or {}).get("funding_pct"),
        "rsi_1d": d1.get("rsi"),
        "atr_pct_1d": d1.get("atr_pct"),
        "vol_ratio_1d": d1.get("vol_ratio"),
        "change_7d": (facts.get("change") or {}).get("7d"),
        "above_ema200_1d": None if price is None or ema200 is None else int(price > ema200),
    }


def store_snapshot(db: Database, run_id: str, facts: dict, ts: str | None = None) -> int:
    """One row per asset of a run's facts.json. A new snapshot in the same run replaces it."""
    market = json.dumps(facts.get("_market") or {})
    assets = {k: v for k, v in facts.items() if not k.startswith("_")}
    for asset, f in assets.items():
        db.upsert(
            "snapshots",
            ("run_id", "asset"),
            run_id=run_id,
            asset=asset,
            ts=ts or now(),
            price=f.get("price"),
            facts=json.dumps(f),
            market=market,
            move_24h=None,
            move_72h=None,
        )
    return len(assets)


def backfill_snapshots(db: Database, settings: Settings) -> int:
    """Import facts.json of runs that predate the snapshots table. Reads only, never rewrites."""
    count = 0
    for run in db.all(
        "SELECT id, started_at FROM runs r WHERE NOT EXISTS "
        "(SELECT 1 FROM snapshots s WHERE s.run_id = r.id)"
    ):
        path = settings.path(settings.runs_dir) / run["id"] / "facts.json"
        if path.exists():
            try:
                count += store_snapshot(
                    db, run["id"], json.loads(path.read_text()), run["started_at"]
                )
            except (ValueError, AttributeError):
                continue
    return count


def fetch(md: MarketData, symbol: str, start_ms: int, pages: int = 6) -> list[Candle]:
    """1h candles from start_ms on, paged past Binance's 1000 per request."""
    out: list[Candle] = []
    cursor = start_ms - HOUR
    for _ in range(pages):
        batch = md.klines(symbol, "1h", 1000, cursor)
        out += [c for c in batch if not out or c.open_time > out[-1].open_time]
        if len(batch) < 1000:
            break
        cursor = batch[-1].open_time + HOUR
    return out


def judge(plan: dict, candles: list[Candle], settings: Settings, now_ms: int) -> dict:
    """Replay a plan; a fill still open after the horizon's hold days resolves as a timeout."""
    ttl = settings.execution.entry_ttl_hours
    out = replay(plan, candles, ttl)
    if out["filled_at"] is None:
        return out
    end = out["filled_at"] + settings.hold_days.days(Horizon(plan["horizon"])) * 24 * HOUR
    closed_late = out["closed_at"] is None or out["closed_at"] >= end
    if closed_late and now_ms >= end:
        cut = replay(plan, [c for c in candles if c.open_time < end], ttl)
        return cut | {"outcome": "timeout", "closed_at": end}
    return out


def close_at(candles: list[Candle], at_ms: int) -> float | None:
    """Close of the 1h candle that holds at_ms, once it has closed."""
    for c in reversed(candles):
        if c.open_time <= at_ms:
            return c.close if at_ms - c.open_time < HOUR else None
    return None


def learn(
    db: Database, settings: Settings, md: MarketData, stale_after: timedelta | None = None
) -> dict:
    """Update outcomes of unresolved ideas and the after-run moves. Candles are fetched once per
    symbol per call. With stale_after, ideas checked more recently than that are skipped."""
    backfill_snapshots(db, settings)
    now_ms = int(datetime.now(UTC).timestamp() * 1000)
    stale_ms = int(stale_after.total_seconds() * 1000) if stale_after else -HOUR
    cutoff = iso(now_ms - stale_ms)
    plans = db.all(
        "SELECT p.* FROM plans p LEFT JOIN outcomes o ON o.plan_id = p.id "
        f"WHERE o.plan_id IS NULL OR (o.outcome NOT IN {RESOLVED} AND o.updated_at < ?) "
        "ORDER BY p.id",
        cutoff,
    )
    snaps = [
        s
        for s in db.all(
            "SELECT run_id, asset, ts, price FROM snapshots "
            "WHERE price IS NOT NULL AND (move_24h IS NULL OR move_72h IS NULL)"
        )
        if ms(s["ts"]) + (WINDOWS["24h"] + 1) * HOUR <= now_ms
    ]
    starts: dict[str, int] = {}
    for symbol, at in [(p["symbol"], p["created_at"]) for p in plans] + [
        (settings.symbol(s["asset"]), s["ts"]) for s in snaps
    ]:
        starts[symbol] = min(starts.get(symbol, ms(at)), ms(at))
    candles: dict[str, list[Candle]] = {}
    for symbol, start in starts.items():
        try:
            candles[symbol] = fetch(md, symbol, start)
        except Exception:
            candles[symbol] = []
    resolved = 0
    for p in plans:
        if not candles[p["symbol"]]:
            continue
        out = judge(p, candles[p["symbol"]], settings, now_ms)
        done = out["outcome"] in RESOLVED
        resolved += done
        snap = db.one(
            "SELECT facts, market FROM snapshots WHERE run_id = ? AND asset = ?",
            p["run_id"],
            p["asset"],
        )
        ctx = context(*(json.loads(snap[k] or "{}") for k in ("facts", "market"))) if snap else {}
        db.upsert(
            "outcomes",
            ("plan_id",),
            plan_id=p["id"],
            run_id=p["run_id"],
            asset=p["asset"],
            side=p["side"],
            horizon=p["horizon"],
            confidence=p["confidence"],
            decision=decision(p),
            outcome=out["outcome"],
            r=out["r"],
            filled_at=iso(out["filled_at"]),
            resolved_at=iso(out["closed_at"]) if done else None,
            updated_at=now(),
            **(ctx or dict.fromkeys(context({}, {}))),
        )
    moves = 0
    for s in snaps:
        series, start = candles[settings.symbol(s["asset"])], ms(s["ts"])
        found = {}
        for key, hours in WINDOWS.items():
            close = close_at(series, start + hours * HOUR)
            if close is not None:
                found[f"move_{key}"] = round((close / s["price"] - 1) * 100, 3)
        if found:
            moves += 1
            sets = ", ".join(f"{k} = ?" for k in found)
            with db.tx() as c:
                c.execute(
                    f"UPDATE snapshots SET {sets} WHERE run_id = ? AND asset = ?",
                    (*found.values(), s["run_id"], s["asset"]),
                )
    return {"ideas": len(plans), "resolved": resolved, "moves": moves}


def bucket(confidence: int) -> str:
    if confidence >= 75:
        return "75+"
    if confidence >= 65:
        return "65-74"
    return "55-64" if confidence >= 55 else "<55"


def summarize(rows: list[dict]) -> dict:
    n = len(rows)
    hits = sum(r["r"] > 0 for r in rows)
    return {
        "n": n,
        "hit_rate": round(hits / n, 3) if n else None,
        "avg_r": round(sum(r["r"] for r in rows) / n, 2) if n else None,
        "enough": n >= MIN_SAMPLE,
    }


def group(rows: list[dict], key: Callable[[dict], str]) -> dict[str, dict]:
    groups: dict[str, list[dict]] = {}
    for r in rows:
        groups.setdefault(key(r), []).append(r)
    return {k: summarize(v) for k, v in sorted(groups.items())}


def moves(values: list[float]) -> dict:
    n = len(values)
    return {
        "n": n,
        "avg_pct": round(sum(values) / n, 2) if n else None,
        "avg_abs_pct": round(sum(abs(v) for v in values) / n, 2) if n else None,
        "up_share": round(sum(v > 0 for v in values) / n, 3) if n else None,
        "enough": n >= MIN_SAMPLE,
    }


def sides(values: list[float]) -> dict:
    bull, bear = sum(v > 0 for v in values), sum(v < 0 for v in values)
    n = bull + bear
    return {
        "n": n,
        "bull": bull,
        "bear": bear,
        "bull_share": round(bull / n, 3) if n else None,
        "enough": n >= MIN_SAMPLE,
    }


def stats(db: Database) -> dict:
    """Calibration of the desk's ideas and of its pass days. Every number carries its n."""
    every = db.all("SELECT * FROM outcomes")
    rows = [r for r in every if r["outcome"] in FILLED]
    pass_moves = db.all(
        "SELECT s.run_id, s.move_24h, s.move_72h FROM snapshots s JOIN runs r ON r.id = s.run_id "
        "WHERE r.status = 'done' AND NOT EXISTS (SELECT 1 FROM plans p WHERE p.run_id = r.id)"
    )
    debated = db.all(
        "SELECT s.move_24h, s.move_72h FROM snapshots s WHERE "
        + " AND ".join(
            "EXISTS (SELECT 1 FROM events e WHERE e.run_id = s.run_id "
            f"AND e.actor = '{actor}' AND e.kind = 'output')"
            for actor in ("bull", "bear")
        )
    )

    def col(src: list[dict], key: str) -> list[float]:
        return [r[f"move_{key}"] for r in src if r[f"move_{key}"] is not None]

    return {
        "min_sample": MIN_SAMPLE,
        "ideas": {
            "total": len(every),
            "filled_and_resolved": len(rows),
            "open": sum(r["outcome"] not in RESOLVED for r in every),
            "expired_unfilled": sum(r["outcome"] == "expired" for r in every),
        },
        "overall": summarize(rows),
        "by_confidence": group(rows, lambda r: bucket(r["confidence"])),
        "by_asset": group(rows, lambda r: r["asset"]),
        "by_horizon": group(rows, lambda r: r["horizon"]),
        "by_side": group(rows, lambda r: r["side"]),
        "by_decision": group(rows, lambda r: r["decision"]),
        "pass_days": {
            "runs": len({r["run_id"] for r in pass_moves}),
            **{k: moves(col(pass_moves, k)) for k in WINDOWS},
        },
        "bull_bear": {k: sides(col(debated, k)) for k in WINDOWS},
    }


def line(s: dict) -> str:
    if not s["enough"]:
        return f"{NOT_ENOUGH} (n {s['n']})"
    return f"hit {s['hit_rate']:.0%}, avg {s['avg_r']:+.2f}R (n {s['n']})"


def report(data: dict) -> str:
    """The stats as short markdown for /review."""
    ideas, n = data["ideas"], data["min_sample"]
    out = [
        f"# Calibration (hit = replay ended above 0R; groups under {n} examples are hidden)",
        f"ideas: {ideas['total']} total, {ideas['filled_and_resolved']} filled and resolved, "
        f"{ideas['open']} still open or waiting, {ideas['expired_unfilled']} expired unfilled",
        f"overall: {line(data['overall'])}",
    ]
    titles = {
        "by_confidence": "By confidence",
        "by_asset": "By asset",
        "by_horizon": "By horizon",
        "by_side": "By side",
        "by_decision": "Taken, passed (cleared risk, not taken), rejected (by risk)",
    }
    for key, title in titles.items():
        out.append(f"## {title}")
        out += [f"- {k}: {line(v)}" for k, v in data[key].items()] or ["- none yet"]
    days = data["pass_days"]
    out.append(f"## Pass days ({days['runs']} runs with zero ideas, per watchlist asset)")
    for k in WINDOWS:
        m = days[k]
        out.append(
            f"- next {k}: avg {m['avg_pct']:+.2f}%, avg size {m['avg_abs_pct']:.2f}%, "
            f"up {m['up_share']:.0%} (n {m['n']})"
            if m["enough"]
            else f"- next {k}: {NOT_ENOUGH} (n {m['n']})"
        )
    out.append("## Bull vs bear (asset up = bull side, down = bear side, after debated runs)")
    for k in WINDOWS:
        b = data["bull_bear"][k]
        out.append(
            f"- next {k}: bull {b['bull']}, bear {b['bear']} (n {b['n']})"
            if b["enough"]
            else f"- next {k}: {NOT_ENOUGH} (n {b['n']})"
        )
    return "\n".join(out) + "\n"


def summary_line(data: dict) -> str | None:
    """One line for book.md, only once the desk has MIN_SAMPLE resolved ideas."""
    if not data["overall"]["enough"]:
        return None
    buckets = [f"{k} {line(v)}" for k, v in data["by_confidence"].items() if v["enough"]]
    return "calibration: " + "; ".join([line(data["overall"]), *buckets])
