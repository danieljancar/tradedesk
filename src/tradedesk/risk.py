import math
from dataclasses import dataclass, field

from tradedesk.binance.market import SymbolRules
from tradedesk.config import Horizon, Market, Settings
from tradedesk.models import Rating, Side, TradeIdea

SPOT_FEE_BUFFER = 0.0015


@dataclass
class Book:
    equity: float
    free_quote: float
    peak_equity: float
    day_pnl: float
    open_risk: float
    open_count: int
    taken: set[tuple[str, str]] = field(default_factory=set)
    allowed: set[str] = field(default_factory=set)
    # equity of the active trading sleeve when part of the account is a long-term core
    sleeve_equity: float | None = None

    @property
    def active_equity(self) -> float:
        return self.equity if self.sleeve_equity is None else self.sleeve_equity


@dataclass
class Verdict:
    ok: bool
    reasons: list[str]
    entry: float = 0
    stop: float = 0
    take_profit: float = 0
    qty: float = 0
    risk_amount: float = 0
    reward_risk: float = 0
    leverage: int = 1

    @property
    def notional(self) -> float:
        return self.qty * self.entry


def account_blocks(settings: Settings, book: Book) -> list[str]:
    limits = settings.risk
    reasons = []
    if book.day_pnl < 0 and -book.day_pnl / book.equity * 100 >= limits.daily_loss_limit_pct:
        reasons.append(
            f"daily loss {book.day_pnl:.2f} hit the {limits.daily_loss_limit_pct}% limit"
        )
    if book.peak_equity and (1 - book.equity / book.peak_equity) * 100 >= limits.max_drawdown_pct:
        reasons.append(f"drawdown from peak is above {limits.max_drawdown_pct}%, desk is paused")
    return reasons


def check(
    idea: TradeIdea,
    settings: Settings,
    book: Book,
    price: float,
    atr: float | None,
    rules: SymbolRules,
) -> Verdict:
    limits = settings.risk
    if book.equity <= 0:
        return Verdict(False, ["no equity on the account"])
    reasons = account_blocks(settings, book)
    s = idea.side.sign

    if book.allowed and idea.asset not in book.allowed:
        reasons.append(f"{idea.asset} is not in today's universe")
    elif not book.allowed and idea.asset not in [a.upper() for a in settings.watchlist]:
        reasons.append(f"{idea.asset} is not on the watchlist")
    if idea.rating in (Rating.HOLD,):
        reasons.append("rating is hold, nothing to place")
    if idea.side is Side.SHORT and settings.market is Market.SPOT:
        reasons.append("shorts need market = futures")
    if idea.side is Side.LONG and idea.rating in (Rating.SELL, Rating.UNDERWEIGHT):
        reasons.append("long idea with a bearish rating")
    if idea.side is Side.SHORT and idea.rating in (Rating.BUY, Rating.OVERWEIGHT):
        reasons.append("short idea with a bullish rating")
    if idea.confidence < limits.min_confidence:
        reasons.append(f"confidence {idea.confidence} below {limits.min_confidence}")
    if settings.market is Market.FUTURES and any(a == idea.asset for a, _ in book.taken):
        reasons.append(f"already have a {idea.asset} position or order, futures net per symbol")
    elif (idea.asset, idea.horizon.value) in book.taken:
        reasons.append(f"already have an open or pending {idea.horizon} trade on {idea.asset}")
    if book.open_count >= limits.max_open_positions:
        reasons.append(
            f"{book.open_count} positions or orders open, max {limits.max_open_positions}"
        )

    entry = price if idea.entry_type == "market" else rules.price(idea.entry)
    stop, take_profit = rules.price(idea.stop), rules.price(idea.take_profit)
    if (entry - stop) * s <= 0 or (take_profit - entry) * s <= 0:
        reasons.append(f"levels invalid against price {price}: stop or target on the wrong side")
        return Verdict(False, reasons)

    distance_pct = abs(entry - price) / price * 100
    if distance_pct > limits.max_entry_distance_pct:
        reasons.append(
            f"entry is {distance_pct:.1f}% from price, max {limits.max_entry_distance_pct}%"
        )
    if idea.entry_type == "limit" and (entry - price) * s > price * 0.002:
        reasons.append(
            "limit entry is past the current price, use a market entry or a better level"
        )
    if (stop - price) * s >= 0:
        reasons.append("stop is already through the current price")

    stop_dist = abs(entry - stop)
    stop_pct = stop_dist / entry * 100
    if stop_pct > limits.max_stop_pct:
        reasons.append(f"stop is {stop_pct:.1f}% away, max {limits.max_stop_pct}%")
    if atr and stop_dist < limits.min_stop_atr * atr:
        reasons.append(
            f"stop {stop_dist:.6g} is tighter than {limits.min_stop_atr} x ATR ({atr:.6g})"
        )
    rr = abs(take_profit - entry) / stop_dist
    if rr < limits.min_reward_risk:
        reasons.append(f"reward/risk {rr:.2f} below {limits.min_reward_risk}")

    risk_amount = position_risk(settings, book, idea.confidence)
    if limits.principal and limits.floor_pct:
        room = book.equity - limits.principal * limits.floor_pct / 100 - book.open_risk
        if room <= 0:
            reasons.append(
                f"equity {book.equity:.2f} with open risk {book.open_risk:.2f} is at the "
                f"protected floor ({limits.floor_pct}% of {limits.principal})"
            )
        risk_amount = max(0.0, min(risk_amount, room))
    if (book.open_risk + risk_amount) / book.active_equity * 100 > limits.max_total_risk_pct:
        reasons.append(
            f"open risk {book.open_risk:.2f} plus this trade exceeds {limits.max_total_risk_pct}%"
        )

    qty = risk_amount / stop_dist if risk_amount > 0 else 0.0
    cap = book.active_equity * limits.max_position_pct / 100
    leverage = 1
    if settings.market is Market.FUTURES:
        # isolated margin: each position gets its own slice of the account as collateral
        slot = book.active_equity / limits.max_open_positions
        cap = min(cap * limits.max_leverage, slot * limits.max_leverage)
        qty = min(qty, cap / entry)
        leverage = max(1, min(limits.max_leverage, math.ceil(qty * entry / slot)))
        liq_pct = 100 / leverage - limits.maintenance_margin_pct
        if stop_pct >= liq_pct * 0.8:
            reasons.append(
                f"stop is {stop_pct:.1f}% away but at {leverage}x the position would be "
                f"liquidated around {liq_pct:.1f}%, move the stop closer or skip"
            )
    else:
        qty = min(qty, cap / entry, book.free_quote * 0.995 / entry)
    qty = rules.qty(qty)
    exit_qty = qty if settings.market is Market.FUTURES else rules.qty(qty * (1 - SPOT_FEE_BUFFER))
    if exit_qty < rules.min_qty or exit_qty * stop < rules.min_notional:
        reasons.append(
            f"size {qty} ({qty * entry:.2f} {settings.quote}) is below the exchange minimum "
            f"{rules.min_notional}"
        )
    return Verdict(
        ok=not reasons,
        reasons=reasons,
        entry=entry,
        stop=stop,
        take_profit=take_profit,
        qty=qty,
        risk_amount=qty * stop_dist,
        reward_risk=round(rr, 2),
        leverage=leverage,
    )


def conviction(settings: Settings, confidence: int | None) -> float:
    """Risk multiplier: 1 at the minimum confidence, confident_risk_x at confident_at and above."""
    limits = settings.risk
    if confidence is None or limits.confident_risk_x <= 1:
        return 1.0
    span = limits.confident_at - limits.min_confidence
    if span <= 0:
        return limits.confident_risk_x if confidence >= limits.confident_at else 1.0
    share = min(1.0, max(0.0, (confidence - limits.min_confidence) / span))
    return 1 + (limits.confident_risk_x - 1) * share


def position_risk(settings: Settings, book: Book, confidence: int | None = None) -> float:
    """Loss at the stop. With a principal set, profits above it are risked at their own rate."""
    limits, equity = settings.risk, book.active_equity
    scale = conviction(settings, confidence)
    if not limits.principal:
        return equity * limits.risk_per_trade_pct / 100 * scale
    on_principal = min(equity, limits.principal) * limits.risk_per_trade_pct / 100
    profit = max(0.0, equity - limits.principal)
    return (on_principal + profit * limits.profit_risk_pct / 100) * scale


def horizon_atr(horizon: Horizon, facts: dict) -> float | None:
    return facts.get("atr_4h") if horizon is Horizon.SHORT else facts.get("atr_1d")
