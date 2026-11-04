"""Performance numbers from the equity table and closed positions. Equity is taken as the last
recorded value of each UTC day. Ratios are annualized with sqrt(365) because crypto trades every
day, and they stay empty until there are MIN_DAYS daily points."""

import math
from collections.abc import Callable
from datetime import UTC, datetime

from tradedesk import macro
from tradedesk.config import Settings
from tradedesk.db import Database
from tradedesk.indicators import Candle

MIN_DAYS = 14
USD_LIKE = {"USD", "USDT", "USDC", "FDUSD"}
FX_SERIES = {"CHF": "DEXSZUS"}

Klines = Callable[[str, str, int, int | None], list[Candle]]


def daily(rows: list[dict]) -> list[tuple[str, float]]:
    last: dict[str, float] = {}
    for r in sorted(rows, key=lambda x: x["ts"]):
        last[r["ts"][:10]] = r["value"]
    return sorted(last.items())


def curve(points: list[tuple[str, float]]) -> list[dict]:
    out, peak = [], 0.0
    for d, v in points:
        peak = max(peak, v)
        dd = (v / peak - 1) * 100 if peak > 0 else 0.0
        out.append({"d": d, "value": round(v, 2), "drawdown_pct": round(dd, 2)})
    return out


def _r(value: float | None, digits: int = 2) -> float | None:
    return None if value is None else round(value, digits)


def equity_metrics(rows: list[dict]) -> dict:
    points = daily(rows)
    if not points:
        return {"days": 0}
    values = [v for _, v in points]
    returns = [(points[i][0], values[i] / values[i - 1] - 1) for i in range(1, len(values))]
    rets = [r for _, r in returns]
    dd = [x["drawdown_pct"] for x in curve(points)]
    sharpe = sortino = None
    if len(points) >= MIN_DAYS and len(rets) > 1:
        mean = sum(rets) / len(rets)
        std = math.sqrt(sum((r - mean) ** 2 for r in rets) / (len(rets) - 1))
        down = math.sqrt(sum(min(r, 0.0) ** 2 for r in rets) / len(rets))
        sharpe = mean / std * math.sqrt(365) if std else None
        sortino = mean / down * math.sqrt(365) if down else None
    best = max(returns, key=lambda x: x[1]) if returns else None
    worst = min(returns, key=lambda x: x[1]) if returns else None
    return {
        "days": len(points),
        "start": points[0][0],
        "end": points[-1][0],
        "start_equity": values[0],
        "end_equity": values[-1],
        "total_return_pct": round((values[-1] / values[0] - 1) * 100, 2),
        "max_drawdown_pct": min(dd),
        "current_drawdown_pct": dd[-1],
        "daily_returns": [{"d": d, "pct": round(r * 100, 3)} for d, r in returns],
        "sharpe": _r(sharpe),
        "sortino": _r(sortino),
        "best_day": {"d": best[0], "pct": round(best[1] * 100, 2)} if best else None,
        "worst_day": {"d": worst[0], "pct": round(worst[1] * 100, 2)} if worst else None,
    }


def r_multiple(p: dict) -> float:
    risk = abs(p["entry_price"] - p["initial_stop"]) * p["qty"]
    return p["pnl"] / risk if risk else 0.0


def _hours(p: dict) -> float:
    opened, closed = (datetime.fromisoformat(p[k]) for k in ("opened_at", "closed_at"))
    return (closed - opened).total_seconds() / 3600


def _group(rows: list[dict]) -> dict:
    n = len(rows)
    return {
        "count": n,
        "pnl": round(sum(p["pnl"] for p in rows), 2),
        "win_rate": round(sum(p["pnl"] > 0 for p in rows) / n, 3) if n else None,
        "avg_r": round(sum(r_multiple(p) for p in rows) / n, 2) if n else None,
    }


def breakdown(rows: list[dict], key: str) -> dict[str, dict]:
    groups: dict[str, list[dict]] = {}
    for p in rows:
        groups.setdefault(str(p.get(key) or "unknown"), []).append(p)
    return {k: _group(v) for k, v in sorted(groups.items())}


def trade_metrics(positions: list[dict]) -> dict:
    rows = [p for p in positions if p["pnl"] is not None]
    n = len(rows)
    wins = [p for p in rows if p["pnl"] > 0]
    losses = [p for p in rows if p["pnl"] <= 0]
    gross_win = sum(p["pnl"] for p in wins)
    gross_loss = -sum(p["pnl"] for p in losses)
    return {
        "count": n,
        "win_rate": round(len(wins) / n, 3) if n else None,
        "profit_factor": round(gross_win / gross_loss, 2) if gross_loss > 0 else None,
        "expectancy_r": round(sum(r_multiple(p) for p in rows) / n, 2) if n else None,
        "expectancy_quote": round((gross_win - gross_loss) / n, 2) if n else None,
        "avg_win_r": round(sum(map(r_multiple, wins)) / len(wins), 2) if wins else None,
        "avg_loss_r": round(sum(map(r_multiple, losses)) / len(losses), 2) if losses else None,
        "avg_hold_hours": round(sum(map(_hours, rows)) / n, 1) if n else None,
        "by": {
            key: breakdown(rows, key)
            for key in ("asset", "horizon", "side", "sleeve", "exit_reason")
        },
    }


def benchmark(points: list[tuple[str, float]], candles: list[Candle]) -> list[dict]:
    """BTC bought with the first day's equity and held, on the equity curve's dates."""
    closes = sorted(
        (datetime.fromtimestamp(c.open_time / 1000, UTC).date().isoformat(), c.close)
        for c in candles
    )
    if not points or not closes:
        return []
    out, i, price = [], 0, None
    for d, _ in points:
        while i < len(closes) and closes[i][0] <= d:
            price = closes[i][1]
            i += 1
        if price is not None:
            out.append({"d": d, "btc": price})
    if not out:
        return []
    start_value, first = dict(points)[out[0]["d"]], out[0]["btc"]
    return [x | {"value": round(start_value * x["btc"] / first, 2)} for x in out]


def _fred_last(series: str) -> tuple[str, float] | None:
    rows = macro._cached(f"fx:{series}", 6 * 3600, lambda: macro.fred(series, days=30))
    return rows[-1] if rows else None


def fx_rate(
    quote: str, base: str, fetch: Callable[[str], tuple[str, float] | None] | None = None
) -> dict:
    """Units of base per unit of quote. USDT and the other dollar coins count as USD."""
    q = "USD" if quote.upper() in USD_LIKE else quote.upper()
    b = "USD" if base.upper() in USD_LIKE else base.upper()
    out = {"quote": quote, "base": base, "rate": None, "as_of": None, "source": None, "note": ""}
    if q == b:
        return out | {"rate": 1.0, "source": "same currency"}
    series = FX_SERIES.get(b)
    if q != "USD" or series is None:
        return out | {"note": f"no exchange rate source for {quote} to {base}"}
    try:
        hit = (fetch or _fred_last)(series)
    except Exception:
        hit = None
    if not hit:
        return out | {"source": f"FRED {series}", "note": f"FRED {series} did not answer"}
    return out | {"rate": hit[1], "as_of": hit[0], "source": f"FRED {series}"}


def report(
    db: Database,
    settings: Settings,
    klines: Klines | None = None,
    fx: dict | None = None,
) -> dict:
    rows = db.all("SELECT ts, value FROM equity ORDER BY ts")
    points = daily(rows)
    closed = db.all("SELECT * FROM positions WHERE status = 'closed' ORDER BY closed_at")
    bench, note = [], ""
    if points and klines is not None:
        start = int(datetime.fromisoformat(points[0][0]).replace(tzinfo=UTC).timestamp() * 1000)
        try:
            bench = benchmark(points, klines(settings.symbol("BTC"), "1d", 1000, start))
        except Exception as e:
            note = f"BTC candles did not load: {e}"
    fx = fx or fx_rate(settings.quote, settings.portfolio.base_currency)
    metrics = equity_metrics(rows)
    rate = fx.get("rate")
    if rate and metrics.get("end_equity") is not None:
        metrics["end_equity_base"] = round(metrics["end_equity"] * rate, 2)
    return {
        "quote": settings.quote,
        "base_currency": settings.portfolio.base_currency,
        "fx": fx,
        "metrics": metrics,
        "trades": trade_metrics(closed),
        "equity": curve(points),
        "benchmark": bench,
        "benchmark_note": note,
    }


def _num(value: float | None, fmt: str) -> str:
    return "n/a" if value is None else format(value, fmt)


def summary(data: dict) -> list[str]:
    m, t, q = data["metrics"], data["trades"], data["quote"]
    if not m.get("days"):
        lines = ["no equity history yet"]
    else:
        lines = [
            f"{m['start']} to {m['end']} ({m['days']} days): {m['start_equity']:.2f} to "
            f"{m['end_equity']:.2f} {q}, return {m['total_return_pct']:+.2f}%",
            f"max drawdown {m['max_drawdown_pct']:.2f}%, now {m['current_drawdown_pct']:.2f}%, "
            f"Sharpe {_num(m['sharpe'], '.2f')}, Sortino {_num(m['sortino'], '.2f')}"
            + ("" if m["sharpe"] is not None else f" (need {MIN_DAYS} days)"),
        ]
        if m["best_day"]:
            lines.append(
                f"best day {m['best_day']['d']} {m['best_day']['pct']:+.2f}%, worst "
                f"{m['worst_day']['d']} {m['worst_day']['pct']:+.2f}%"
            )
    fx = data["fx"]
    if fx["rate"] and m.get("days"):
        lines.append(
            f"equity {m['end_equity_base']:.2f} {data['base_currency']} at {fx['rate']:.4f} "
            f"({fx['source']}, {fx['as_of'] or 'today'})"
        )
    elif fx["note"]:
        lines.append(f"no {data['base_currency']} value: {fx['note']}")
    if data["benchmark"]:
        b = data["benchmark"]
        lines.append(
            f"BTC buy and hold over the same days: {b[0]['value']:.2f} to {b[-1]['value']:.2f}"
        )
    elif data["benchmark_note"]:
        lines.append(data["benchmark_note"])
    lines.append(trade_line(t, q))
    for key, groups in t["by"].items():
        if groups:
            lines.append(
                f"by {key}: "
                + ", ".join(
                    f"{k} {g['count']} trades {g['pnl']:+.2f} avg {_num(g['avg_r'], '+.2f')}R"
                    for k, g in groups.items()
                )
            )
    return lines


def trade_line(t: dict, quote: str) -> str:
    if not t["count"]:
        return "closed trades: none yet"
    return (
        f"closed trades: {t['count']}, win rate {t['win_rate']:.0%}, profit factor "
        f"{_num(t['profit_factor'], '.2f')}, expectancy {t['expectancy_r']:+.2f}R "
        f"({t['expectancy_quote']:+.2f} {quote}), avg hold {t['avg_hold_hours']:.0f}h"
    )


def book_lines(db: Database, quote: str) -> list[str]:
    """Two lines of key numbers for book.md, from the database only."""
    m = equity_metrics(db.all("SELECT ts, value FROM equity ORDER BY ts"))
    closed = db.all("SELECT * FROM positions WHERE status = 'closed'")
    t = trade_metrics(closed)
    if not m.get("days"):
        first = "performance: no equity history yet"
    else:
        first = (
            f"performance over {m['days']} days: return {m['total_return_pct']:+.2f}%, max "
            f"drawdown {m['max_drawdown_pct']:.2f}%, now {m['current_drawdown_pct']:.2f}% under "
            f"peak, Sharpe {_num(m['sharpe'], '.2f')}"
        )
    return [first, trade_line(t, quote)]
