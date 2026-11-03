"""Replay a trade plan on real candles after it was made: did it fill, and did it hit the stop or
the target first? Used for the report, so the desk can be judged on every idea, taken or not."""

from collections.abc import Sequence
from datetime import datetime

from tradedesk.indicators import Candle


def _ms(iso: str) -> int:
    return int(datetime.fromisoformat(iso).timestamp() * 1000)


def replay(plan: dict, candles: Sequence[Candle], entry_ttl_hours: float = 24) -> dict:
    """Walk the candles after the plan was made. Stop and target in one candle is a stop."""
    sign = 1 if plan["side"] == "long" else -1
    entry, stop, target = plan["entry"], plan["stop"], plan["take_profit"]
    start = _ms(plan["created_at"])
    ttl_end = start + entry_ttl_hours * 3_600_000
    after = [c for c in candles if c.open_time >= start - 3_600_000 + 1]
    filled_at = None
    fill_price = entry
    for c in after:
        if filled_at is None:
            if plan["entry_type"] == "market":
                filled_at, fill_price = c.open_time, c.open
            elif (sign > 0 and c.low <= entry) or (sign < 0 and c.high >= entry):
                filled_at = c.open_time
            elif c.open_time > ttl_end:
                return {"outcome": "expired", "r": 0.0, "filled_at": None, "closed_at": c.open_time}
            else:
                continue
        hit_stop = c.low <= stop if sign > 0 else c.high >= stop
        hit_target = c.high >= target if sign > 0 else c.low <= target
        risk = abs(fill_price - stop) or 1e-12
        if hit_stop:
            r = (stop - fill_price) * sign / risk
            return {
                "outcome": "stop",
                "r": round(r, 2),
                "filled_at": filled_at,
                "closed_at": c.open_time,
            }
        if hit_target:
            r = (target - fill_price) * sign / risk
            return {
                "outcome": "target",
                "r": round(r, 2),
                "filled_at": filled_at,
                "closed_at": c.open_time,
            }
    if filled_at is None:
        return {"outcome": "waiting", "r": 0.0, "filled_at": None, "closed_at": None}
    last = after[-1].close
    r = (last - fill_price) * sign / (abs(fill_price - stop) or 1e-12)
    return {
        "outcome": "open",
        "r": round(r, 2),
        "filled_at": filled_at,
        "closed_at": None,
        "mark": last,
    }
