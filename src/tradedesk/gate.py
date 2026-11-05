"""Decides whether an hourly slot needs a full agent run. A run costs tokens; a quiet market
with nothing to act on doesn't need one. Stops, targets and trailing run in the sync either way."""

import json
import re
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from tradedesk import wire

if TYPE_CHECKING:
    from tradedesk.desk import Desk

MOVERS = re.compile(
    r"\b(fed|fomc|powell|rate cut|rate hike|inflation|cpi|payrolls|tariff|sec|etf|stablecoin|"
    r"recession|hack|exploit|liquidat\w*|bankrupt\w*|ban)\b",
    re.I,
)


def last_run(desk: "Desk") -> dict | None:
    return desk.db.one("SELECT * FROM runs WHERE status = 'done' ORDER BY started_at DESC LIMIT 1")


def reasons(desk: "Desk", now: datetime | None = None) -> list[str]:
    """Why a run should happen now. Empty means skip."""
    cfg = desk.settings.gate
    if not cfg.enabled:
        return ["the gate is off"]
    run = last_run(desk)
    if run is None:
        return ["no finished run yet"]
    now = now or datetime.now(UTC)
    started = datetime.fromisoformat(run["started_at"])
    hours = (now - started).total_seconds() / 3600
    out = []
    if hours >= cfg.max_gap_hours:
        out.append(f"last run {hours:.1f}h ago")
    facts_path = desk.run_dir(run["id"]) / "facts.json"
    facts = json.loads(facts_path.read_text()) if facts_path.exists() else {}
    for asset, f in facts.items():
        then, atr = f.get("price"), f.get("atr_4h")
        if not then or not atr:
            continue
        try:
            price = desk.broker.price(desk.settings.symbol(asset))
        except Exception:
            continue
        moved = abs(price - then) / atr
        if moved >= cfg.move_atr:
            out.append(f"{asset} moved {moved:.1f} 4h ATRs since the last run")
    since = started.timestamp()
    news = [h for h in wire.headlines() if h["ts"] > since and MOVERS.search(h["title"])]
    if len(news) >= cfg.headlines:
        out.append(f"{len(news)} market-moving headlines since the last run")
    if desk.db.all("SELECT id FROM plans WHERE status = 'proposed'"):
        out.append("plans waiting for approval")
    return out
