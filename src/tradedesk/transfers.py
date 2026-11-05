"""Keeps the spot and futures wallets at the target split by moving free quote between them.
Only free money moves: never margin held by open futures positions or coins in spot trades."""

from datetime import UTC, datetime, timedelta
from math import floor
from typing import TYPE_CHECKING

from tradedesk.config import Mode

if TYPE_CHECKING:
    from tradedesk.desk import Desk

COOLDOWN = timedelta(hours=6)


def plan(spot: float, futures: float, spot_free: float, futures_free: float, cfg) -> float:
    """Amount to move: positive into futures, negative back to spot, 0 when inside the band."""
    total = spot + futures
    if total <= 0:
        return 0.0
    target = total * cfg.futures_pct / 100
    if abs(futures - target) / total * 100 < cfg.band_pct:
        return 0.0
    if futures < target:
        room = spot_free - spot * cfg.keep_free_pct / 100
        amount = min(target - futures, room)
    else:
        room = futures_free - futures * cfg.keep_free_pct / 100
        amount = -min(futures - target, room)
    amount = floor(abs(amount) * 100) / 100 * (1 if amount > 0 else -1)
    return amount if abs(amount) >= cfg.min_amount else 0.0


def recent(desk: "Desk") -> bool:
    row = desk.db.one("SELECT MAX(ts) AS ts FROM flows WHERE kind = 'transfer'")
    if not row or not row["ts"]:
        return False
    return datetime.now(UTC) - datetime.fromisoformat(row["ts"]) < COOLDOWN


def balance(spot: "Desk", futures: "Desk") -> list[str]:
    cfg = spot.settings.transfers
    if recent(spot):
        return []
    amount = plan(
        spot.broker.equity(),
        futures.broker.equity(),
        spot.broker.free_quote(),
        futures.broker.free_quote(),
        cfg,
    )
    if not amount:
        return []
    quote = spot.settings.quote
    if spot.settings.mode is Mode.LIVE:
        spot.broker.client.signed(
            "POST",
            "/sapi/v1/asset/transfer",
            type="MAIN_UMFUTURE" if amount > 0 else "UMFUTURE_MAIN",
            asset=quote,
            amount=f"{abs(amount):.2f}",
        )
    elif spot.settings.mode is Mode.TESTNET:
        return [f"would move {abs(amount):.2f} {quote}, the testnet has no wallet transfers"]
    # the flow and the first equity after it share a second that no earlier sample can have
    at = (datetime.now(UTC) + timedelta(seconds=1)).isoformat(timespec="seconds")
    spot.db.record_flow(-amount, "transfer", "to futures" if amount > 0 else "from futures", at)
    futures.db.record_flow(amount, "transfer", "from spot" if amount > 0 else "to spot", at)
    for desk in (spot, futures):
        desk.db.record_equity(desk.broker.equity(), at)
    direction = "spot to futures" if amount > 0 else "futures to spot"
    spot.log(
        "exchange",
        "order",
        f"Moved {abs(amount):.2f} {quote} from {direction}",
        f"target split {100 - cfg.futures_pct:g}% spot, {cfg.futures_pct:g}% futures",
    )
    return [f"moved {abs(amount):.2f} {quote} from {direction}"]
