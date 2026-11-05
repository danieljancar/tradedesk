"""Trailing stops: lock in a winning trade as it runs. Pure math, the desk moves the order."""

from dataclasses import dataclass

from tradedesk.config import Trailing

FEE_PCT = 0.1


@dataclass(frozen=True)
class Move:
    stop: float
    reason: str


def next_stop(
    side: str,
    entry: float,
    initial_stop: float,
    stop: float,
    price: float,
    atr: float | None,
    cfg: Trailing,
) -> Move | None:
    """The stop the trade should have now, or None when the current one is still right."""
    sign = 1 if side == "long" else -1
    risk = abs(entry - initial_stop)
    if not cfg.enabled or risk <= 0:
        return None
    gain_r = (price - entry) * sign / risk
    candidates: list[Move] = []
    if gain_r >= cfg.breakeven_r:
        breakeven = entry * (1 + sign * 2 * FEE_PCT / 100)
        candidates.append(Move(breakeven, f"up {gain_r:.1f}R, stop to break-even after fees"))
    if gain_r >= cfg.trail_start_r and atr:
        trail = price - sign * cfg.trail_atr * atr
        lock = entry + sign * cfg.lock_pct / 100 * (price - entry)
        best = max(trail, lock) if sign > 0 else min(trail, lock)
        how = (
            f"{cfg.trail_atr:g} ATR behind price"
            if best == trail
            else f"keeps {cfg.lock_pct:g}% of the gain"
        )
        candidates.append(Move(best, f"up {gain_r:.1f}R, trailing {how}"))
    if not candidates:
        return None
    move = max(candidates, key=lambda m: m.stop * sign)
    gap = 0.3 * atr if atr else price * 0.003
    limit = price - sign * gap
    if (move.stop - limit) * sign > 0:
        move = Move(limit, move.reason)
    step = cfg.min_step_atr * atr if atr else price * 0.001
    if (move.stop - stop) * sign < step:
        return None
    return move
