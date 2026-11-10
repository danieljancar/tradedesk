import os
import subprocess
import time
from datetime import datetime
from functools import cache
from pathlib import Path
from typing import Annotated

import typer

from tradedesk import notify, ticker
from tradedesk.config import linked_settings, settings
from tradedesk.db import Database
from tradedesk.desk import Desk

app = typer.Typer(no_args_is_help=True, add_completion=False)
run_app = typer.Typer(no_args_is_help=True)
app.add_typer(run_app, name="run", help="Start and finish a daily run.")


@cache
def desk() -> Desk:
    s = settings()
    d = Desk(s, Database(s.path(s.db_path)))
    if (fs := linked_settings(s)) is not None:
        d.link(Desk(fs, Database(fs.path(fs.db_path))))
    notify.attach(d)
    return d


def pick(futures: bool) -> Desk:
    d = desk()
    if futures and d.linked is None:
        raise typer.BadParameter("no futures_desk is set in the config")
    return d.linked if futures else d


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
    """Prices, indicators, levels and derivatives for today's assets."""
    say(str(desk().write_snapshot()))


@app.command()
def news() -> None:
    """Headlines from the last 36 hours, sorted by asset."""
    say(str(desk().write_news()))


@app.command("ticker")
def ticker_data() -> None:
    """Data for the daily market brief, and the earlier briefs to build on."""
    root = Path("data")
    say(str(ticker.write_data(root)))
    for path in ticker.briefs(root)[: ticker.KEEP]:
        say(str(path))
    say(str(ticker.folder(root) / "calendar.md"))


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
        if desk().linked is not None:
            label = f"{r['venue']} {label}"
        detail = "; ".join(r["reasons"]) or (
            f"qty {r['qty']:g} risk {r['risk']:.2f} R/R {r['rr']}" if "qty" in r else ""
        )
        say(f"{label}: {r['status']} {detail}".rstrip())


@app.command()
def precheck(file: Path) -> None:
    """The risk check on a plans.json without recording anything. Fix and run again."""
    for r in desk().preview_plans(file):
        detail = "; ".join(r["reasons"]) or f"qty {r['qty']:g} risk {r['risk']:.2f} R/R {r['rr']}"
        say(f"{r['venue']} {r['asset']} {r['side']}: {'passes' if r['ok'] else 'fails'} {detail}")


@app.command()
def plans(status: str = "proposed") -> None:
    """List plans by status."""
    main = desk()
    rows = [
        {**p, "venue": d.settings.market.value}
        for d in (main, main.linked)
        if d is not None
        for p in d.db.all("SELECT * FROM plans WHERE status = ? ORDER BY id", status)
    ]
    say(
        [
            f"{p['venue'] + ' ' if main.linked else ''}{p['id']} {p['asset']} {p['side']} "
            f"{p['horizon']} entry {p['entry']:g} stop "
            f"{p['stop']:g} target {p['take_profit']:g} qty {p['qty']:g} R/R {p['reward_risk']}"
            for p in rows
        ]
        or f"no {status} plans"
    )


@app.command()
def approve(plan_id: int, futures: bool = False) -> None:
    pick(futures).approve(plan_id)
    say(f"plan {plan_id} approved")


@app.command()
def reject(plan_id: int, futures: bool = False) -> None:
    pick(futures).reject(plan_id)
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
def wake(at: str, note: str) -> None:
    """Schedule an extra desk run at an ISO time (UTC unless it has an offset), with the reason."""
    say(desk().wake(datetime.fromisoformat(at), note))


@app.command()
def entries() -> None:
    """Check only the entries waiting for a price. Meant for a job every minute."""
    d = desk()
    lines = d.entries()
    # scheduled runs start from here, the job that already runs every minute
    for w in d.due_wakeups():
        env = os.environ | {"FORCE": "1", "WAKE_NOTE": w["note"]}
        subprocess.Popen(["bash", "scripts/daily.sh"], env=env, start_new_session=True)
        lines.append(f"woke the desk: {w['note']}")
    if lines:
        say(lines)


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
    main = desk()
    for d in (main, main.linked):
        if d is None:
            continue
        b = d.book()
        say(
            f"{d.settings.mode} {d.settings.market} | equity {b.equity:.2f} | free "
            f"{b.free_quote:.2f} | open risk {b.open_risk:.2f} | realized today {b.day_pnl:+.2f}"
        )
        for p in d.db.open_positions():
            say(
                f"  position {p['id']} {p['asset']} {p['side']} {p['qty']:g} @ "
                f"{p['entry_price']:g} stop {p['stop']:g} target {p['take_profit']:g}"
            )
        for p in d.db.pending_plans():
            say(f"  plan {p['id']} {p['asset']} {p['status']} entry {p['entry']:g}")


@app.command()
def adopt(plan_id: int, futures: bool = False) -> None:
    """Take over a position that is open on the exchange but missing in the desk."""
    say(pick(futures).adopt(plan_id))


@app.command()
def close(position_id: int, reason: str = "manual", futures: bool = False) -> None:
    pick(futures).close(position_id, reason)
    say(f"position {position_id} closed")


@app.command()
def stop(position_id: int, price: float, reason: str = "manual", futures: bool = False) -> None:
    """Move a stop in the trade's favor."""
    say(str(pick(futures).tighten(position_id, price, reason)))


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


@app.command()
def scan() -> None:
    """Scan the spot market for movers and write today's universe."""
    say(str(desk().write_universe()))


@app.command()
def bot() -> None:
    """Telegram bot: approve plans, /status, /report, /kill and /flatten from your phone."""
    from tradedesk.bot import Bot

    d = desk()
    telegram = notify.from_env()
    if telegram is None:
        say("set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env first")
        raise typer.Exit(1)
    say("bot polling, Ctrl-C to stop")
    Bot(d, telegram, d.settings.path(d.settings.db_path).parent / "telegram_offset").run()


@app.command()
def report(send: bool = False) -> None:
    """Short digest: equity and 24h change, open positions, waiting plans, the latest run."""
    d = desk()
    say(notify.digest(d))
    if not send:
        return
    telegram = notify.from_env()
    if telegram is None:
        say("set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env first")
        raise typer.Exit(1)
    telegram.send(notify.digest(d, html=True))
    say("sent")


@app.command()
def rebalance(propose: bool = False) -> None:
    """Core sleeve targets against holdings. --propose turns the gaps into plans and trims."""
    from tradedesk import portfolio

    d = desk()
    if d.settings.portfolio.core_pct <= 0:
        say("core sleeve is off, set [portfolio] core_pct and core_targets in desk.toml")
        return
    r = d.rebalance(propose)
    say([portfolio.row_line(row) for row in r["rows"]])
    for p in r["plans"]:
        say(f"plan {p['id']} buy {p['asset']}: {p['status']} {'; '.join(p['reasons'])}".rstrip())
    for t in r["trims"]:
        say(f"trim {t['id']} sells position {t['position']} ({t['asset']}, {t['value']:.2f})")
    if propose and (r["plans"] or r["trims"]):
        say("approve with `desk approve ID` and `desk trim ID`, then `desk execute`")


@app.command()
def trim(trim_id: int, reject: bool = False) -> None:
    """Approve a proposed core trim, or drop it with --reject."""
    from tradedesk import portfolio

    if reject:
        portfolio.reject_trim(desk(), trim_id)
        say(f"trim {trim_id} dropped")
        return
    portfolio.approve_trim(desk(), trim_id)
    say(f"trim {trim_id} approved, `desk execute` sends it")


@app.command()
def analytics() -> None:
    """Return, drawdown, Sharpe, trade stats and BTC buy and hold over the same days."""
    from tradedesk import analytics as perf
    from tradedesk.binance import market_data

    d = desk()
    say(perf.summary(perf.report(d.db, d.settings, market_data(d.settings).klines)))


@app.command()
def gate() -> None:
    """Exit 0 when this slot needs a full agent run, 1 when the market is quiet."""
    from tradedesk import gate as g

    why = g.reasons(desk())
    say("; ".join(why) if why else "quiet, skipping the agent run")
    raise typer.Exit(0 if why else 1)
