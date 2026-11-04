"""Named sets of risk limits. A profile fills every limit the config file doesn't set itself."""

PROFILES: dict[str, dict[str, float | int]] = {
    "conservative": {
        "risk_per_trade_pct": 0.5,
        "max_total_risk_pct": 3.0,
        "max_open_positions": 4,
        "max_position_pct": 20.0,
        "max_leverage": 2,
        "min_reward_risk": 2.5,
        "min_confidence": 65,
        "daily_loss_limit_pct": 2.0,
        "max_drawdown_pct": 10.0,
    },
    "balanced": {
        "risk_per_trade_pct": 1.0,
        "max_total_risk_pct": 4.0,
        "max_open_positions": 4,
        "max_position_pct": 25.0,
        "max_leverage": 3,
        "min_reward_risk": 2.0,
        "min_confidence": 60,
        "daily_loss_limit_pct": 3.0,
        "max_drawdown_pct": 15.0,
    },
    "aggressive": {
        "risk_per_trade_pct": 2.0,
        "max_total_risk_pct": 10.0,
        "max_open_positions": 8,
        "max_position_pct": 40.0,
        "max_leverage": 5,
        "min_reward_risk": 1.5,
        "min_confidence": 50,
        "daily_loss_limit_pct": 6.0,
        "max_drawdown_pct": 25.0,
    },
}


def resolve(risk: dict) -> dict:
    """Profile values under the explicitly set keys."""
    name = risk.get("profile")
    if not name:
        return risk
    if name not in PROFILES:
        raise ValueError(f"unknown risk profile {name!r}, pick one of {', '.join(PROFILES)}")
    return {**PROFILES[name], **risk}


def explicit(risk: dict) -> dict:
    """The keys worth writing back: the profile name and whatever differs from it."""
    name = risk.get("profile")
    if not name or name not in PROFILES:
        return risk
    base = PROFILES[name]
    return {k: v for k, v in risk.items() if k not in base or v != base[k]}
