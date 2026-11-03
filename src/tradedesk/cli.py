import time
from functools import cache
from pathlib import Path
from typing import Annotated

import typer

from tradedesk.config import settings
from tradedesk.db import Database
from tradedesk.desk import Desk

app = typer.Typer(no_args_is_help=True, add_completion=False)
run_app = typer.Typer(no_args_is_help=True)
app.add_typer(run_app, name="run", help="Start and finish a daily run.")


@cache
def desk() -> Desk:
    s = settings()
    return Desk(s, Database(s.path(s.db_path)))


def say(lines: list[str] | str) -> None:
    typer.echo("\n".join(lines) if isinstance(lines, list) else lines)


@run_app.command("start")
def run_start() -> None:
    d = desk()
    run_id = d.start_run()
    say(f"run {run_id} dir {d.run_dir(run_id)}")


@run_app.command("finish")
def run_finish(summary_file: Path) -> None:
    desk().finish_run(summary_file.read_text())
    say("run finished")


@run_app.command("recover")
def run_recover() -> None:
    """Finish the latest run if the agents stopped half way: check, post, execute, finish."""
    d = desk()
    run = d.db.latest_run()
    if not run or run["status"] != "running":
        say("nothing to recover")
        return
    folder, events = d.run_dir(run["id"]), d.db.events(run["id"])
    done = {(e["actor"], e["kind"]) for e in events}
    reads = ["technical", "news", "bull", "bear", "book"]
    for actor, name in (
        ("technical", "technical.md"),
        ("news", "news-read.md"),
        ("bull", "bull.md"),
        ("bear", "bear.md"),
    ):
        if (folder / name).exists() and (actor, "output") not in done:
            d.post(actor, folder / name, reads=[])
    plans = folder / "plans.json"
    if plans.exists() and not any(e["actor"] == "risk" and e["kind"] != "start" for e in events):
        d.check_plans(plans)
    decision = folder / "decision.md"
    if decision.exists() and ("pm", "output") not in done:
        d.post("pm", decision, reads=reads)
    d.execute()
    summary = folder / "summary.md"
    d.finish_run(
        summary.read_text() if summary.exists() else "Run stopped early, finished by recover."
    )
    say(f"recovered {run['id']}")


@app.command()
def snapshot() -> None:
    """Prices, indicators, levels and derivatives for the watchlist."""
    say(str(desk().write_snapshot()))


@app.command()
def news() -> None:
    """Headlines from the last 36 hours, sorted by asset."""
    say(str(desk().write_news()))


@app.command()
def book() -> None:
    """Equity, open positions, pending entries, recent results and lessons."""
    say(str(desk().write_book()))


@app.command()
def post(
    actor: str,
    file: Annotated[Path | None, typer.Argument()] = None,
    start: bool = False,
    reads: str = "",
) -> None:
    """Record an agent's start or output for the live view."""
    desk().post(actor, file, start=start, reads=[r for r in reads.split(",") if r])


@app.command()
def check(file: Path) -> None:
    """Validate a plans.json and size every idea with the risk rules."""
    for r in desk().check_plans(file):
        label = f"plan {r['id']} {r['asset']}" if "id" in r else f"position {r['position']}"
        detail = "; ".join(r["reasons"]) or (
            f"qty {r['qty']:g} risk {r['risk']:.2f} R/R {r['rr']}" if "qty" in r else ""
        )
        say(f"{label}: {r['status']} {detail}".rstrip())


@app.command()
def plans(status: str = "proposed") -> None:
    """List plans by status."""
    rows = desk().db.all("SELECT * FROM plans WHERE status = ? ORDER BY id", status)
    say(
        [
            f"{p['id']} {p['asset']} {p['side']} {p['horizon']} entry {p['entry']:g} stop "
            f"{p['stop']:g} target {p['take_profit']:g} qty {p['qty']:g} R/R {p['reward_risk']}"
            for p in rows
        ]
        or f"no {status} plans"
    )


@app.command()
def approve(plan_id: int) -> None:
    desk().approve(plan_id)
    say(f"plan {plan_id} approved")


@app.command()
def reject(plan_id: int) -> None:
    desk().reject(plan_id)
    say(f"plan {plan_id} dropped")


@app.command()
def execute() -> None:
    """Send approved plans to the exchange with their stops."""
    say(desk().execute() or "nothing approved")


@app.command()
def sync() -> None:
    """Check fills, stops, targets, expired entries and hold times."""
    say(desk().sync() or "nothing changed")


@app.command()
def learn() -> None:
    """Replay every unresolved idea on real 1h candles and record what followed each run."""
    r = desk().learn()
    say(f"{r['ideas']} ideas checked, {r['resolved']} resolved, {r['moves']} after-run moves")


@app.command()
def stats() -> None:
    """Calibration report: hit rate and R by confidence, asset, horizon, side and decision."""
    from tradedesk import learning

    d = desk()
    try:
        d.learn()
    except Exception as e:
        say(f"(outcomes not updated, Binance did not answer: {e})")
    say(learning.report(learning.stats(d.db)).rstrip())


@app.command()
def watch(every: int = 300) -> None:
    """Keep syncing, for futures entries that wait for a price."""
    while True:
        for line in desk().sync():
            say(line)
        time.sleep(every)


@app.command()
def status() -> None:
    d = desk()
    b = d.book()
    say(
        f"{d.settings.mode} {d.settings.market} | equity {b.equity:.2f} | open risk "
        f"{b.open_risk:.2f} | realized today {b.day_pnl:+.2f}"
    )
    for p in d.db.open_positions():
        say(
            f"position {p['id']} {p['asset']} {p['side']} {p['qty']:g} @ {p['entry_price']:g} "
            f"stop {p['stop']:g} target {p['take_profit']:g}"
        )
    for p in d.db.pending_plans():
        say(f"plan {p['id']} {p['asset']} {p['status']} entry {p['entry']:g}")


@app.command()
def close(position_id: int, reason: str = "manual") -> None:
    desk().close(position_id, reason)
    say(f"position {position_id} closed")


@app.command()
def stop(position_id: int, price: float, reason: str = "manual") -> None:
    """Move a stop in the trade's favor."""
    say(str(desk().tighten(position_id, price, reason)))


@app.command()
def kill(flatten: bool = False) -> None:
    """Cancel every pending order, and with --flatten close every position."""
    say(desk().kill(flatten) or "nothing to cancel")


@app.command()
def journal(days: int = 30) -> None:
    """Closed trades and stats for the review."""
    rows = desk().db.all(
        "SELECT p.*, l.thesis, l.confidence FROM positions p JOIN plans l ON l.id = p.plan_id "
        "WHERE p.status = 'closed' AND p.closed_at >= date('now', ?) ORDER BY p.closed_at",
        f"-{days} days",
    )
    if not rows:
        say("no closed trades in that window")
        return
    wins = [r for r in rows if r["pnl"] > 0]
    total = sum(r["pnl"] for r in rows)
    say(f"{len(rows)} trades, {len(wins)} wins ({len(wins) / len(rows):.0%}), net {total:+.2f}")
    for r in rows:
        risk = abs(r["entry_price"] - r["initial_stop"]) * r["qty"]
        r_mult = r["pnl"] / risk if risk else 0
        say(
            f"{r['closed_at'][:10]} {r['asset']} {r['side']} {r['horizon']} conf {r['confidence']} "
            f"{r['exit_reason']} {r['pnl']:+.2f} ({r_mult:+.1f}R) | {r['thesis']}"
        )


@app.command()
def serve(port: int = 8420, host: str = "127.0.0.1") -> None:
    """Dashboard with the live agent view."""
    import uvicorn

    from tradedesk.web.app import create_app

    uvicorn.run(create_app(desk()), host=host, port=port, log_level="warning")


@app.command()
def demo(port: int = 8421, pause: float = 1.6) -> None:
    """Replay a made-up run on a separate database to see the trading floor."""
    import uvicorn

    from tradedesk import demo as replay
    from tradedesk.web.app import create_app

    s = settings()
    d = Desk(s, replay.demo_db(s.path(s.db_path).with_name("demo.db")))
    replay.start(d, pause)
    say(f"demo on http://127.0.0.1:{port}")
    uvicorn.run(create_app(d), host="127.0.0.1", port=port, log_level="warning")
