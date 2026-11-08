import os
import tomllib
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from tradedesk import profiles

ROOT = Path(os.environ.get("DESK_HOME", Path.cwd()))


class Mode(StrEnum):
    PAPER = "paper"
    TESTNET = "testnet"
    LIVE = "live"


class Market(StrEnum):
    SPOT = "spot"
    FUTURES = "futures"


class Horizon(StrEnum):
    SHORT = "short"
    MID = "mid"
    LONG = "long"


class RiskLimits(BaseModel):
    risk_per_trade_pct: float = Field(1.0, gt=0, le=5)
    max_open_positions: int = Field(4, ge=1)
    max_total_risk_pct: float = Field(4.0, gt=0, le=20)
    max_position_pct: float = Field(25.0, gt=0, le=100)
    max_leverage: int = Field(3, ge=1, le=20)
    # futures margin per position as a share of the wallet; unset, it's an even split over
    # max_open_positions. Leverage is what it takes to fit the position into that margin
    margin_slot_pct: float | None = Field(None, gt=0, le=100)
    min_reward_risk: float = Field(2.0, ge=1)
    daily_loss_limit_pct: float = Field(3.0, gt=0, le=25)
    max_drawdown_pct: float = Field(15.0, gt=0, le=50)
    min_stop_atr: float = Field(0.5, ge=0)
    max_stop_pct: float = Field(15.0, gt=0)
    min_confidence: int = Field(60, ge=0, le=100)
    max_entry_distance_pct: float = Field(8.0, gt=0)
    # House money: principal is risked at risk_per_trade_pct, profits above it at profit_risk_pct.
    # 0 suits a wallet that starts empty and is filled by transfers
    principal: float | None = Field(None, ge=0)
    profit_risk_pct: float = Field(0.0, ge=0, le=25)
    # Conviction: risk grows from 1x at min_confidence to confident_risk_x at confident_at.
    confident_risk_x: float = Field(1.0, ge=1, le=3)
    confident_at: int = Field(85, ge=1, le=100)
    # Share of the principal that open stops may never put at risk, all stops hit at once.
    floor_pct: float = Field(0.0, ge=0, le=100)
    # Futures: maintenance margin used to estimate the liquidation price (isolated margin).
    maintenance_margin_pct: float = Field(0.5, ge=0, le=10)
    # conservative, balanced or aggressive: fills every limit this table doesn't set.
    profile: str | None = None

    @model_validator(mode="before")
    @classmethod
    def apply_profile(cls, data):
        return profiles.resolve(data) if isinstance(data, dict) else data


class HoldLimits(BaseModel):
    short: int = 3
    mid: int = 21
    long: int = 120

    def days(self, horizon: Horizon) -> int:
        return getattr(self, horizon.value)


class Execution(BaseModel):
    auto_execute: bool = False
    close_expired: bool = True
    entry_ttl_hours: int = 24


class Trailing(BaseModel):
    enabled: bool = True
    breakeven_r: float = Field(1.0, gt=0)
    trail_start_r: float = Field(1.5, gt=0)
    trail_atr: float = Field(2.0, gt=0)
    lock_pct: float = Field(50.0, ge=0, lt=100)
    min_step_atr: float = Field(0.25, ge=0)


class Transfers(BaseModel):
    """Keeps the spot and futures wallets at a target split by moving free USDT between them."""

    enabled: bool = False
    futures_pct: float = Field(35.0, gt=0, lt=100)
    band_pct: float = Field(10.0, gt=0, le=50)
    min_amount: float = Field(5.0, gt=0)
    keep_free_pct: float = Field(10.0, ge=0, le=50)


class Gate(BaseModel):
    """Skips the hourly agent run when the market is quiet. The sync still runs every time."""

    enabled: bool = False
    move_atr: float = Field(1.0, gt=0)
    max_gap_hours: float = Field(4.0, gt=0)
    headlines: int = Field(2, ge=1)


class Universe(BaseModel):
    enabled: bool = True
    min_quote_volume: float = Field(20_000_000, ge=0)
    top: int = Field(6, ge=0)
    max_assets: int = Field(12, ge=1)
    always: list[str] = []
    exclude: list[str] = []
    # Binance product tags to leave out of the scan, bStocks are tokenized US stocks
    exclude_tags: list[str] = ["bStocks"]
    include_gold: bool = True


NotifyEvent = Literal["proposed", "fill", "exit", "error", "run", "kill"]


class Notify(BaseModel):
    telegram: bool = False
    events: list[NotifyEvent] = ["proposed", "fill", "exit", "error", "run", "kill"]
    quiet_hours: str = ""

    @field_validator("quiet_hours")
    @classmethod
    def _hours(cls, v: str) -> str:
        v = v.strip()
        if not v:
            return v
        start, sep, end = v.partition("-")
        if not sep or not (start.isdigit() and end.isdigit()):
            raise ValueError('quiet_hours looks like "23-07"')
        if not (0 <= int(start) <= 23 and 0 <= int(end) <= 23):
            raise ValueError("quiet_hours uses hours 0 to 23")
        return v

    def quiet(self, hour: int) -> bool:
        if not self.quiet_hours:
            return False
        start, end = (int(x) for x in self.quiet_hours.split("-"))
        if start == end:
            return False
        return start <= hour < end if start < end else hour >= start or hour < end


class Portfolio(BaseModel):
    core_pct: float = Field(0.0, ge=0, lt=100)
    core_targets: dict[str, float] = {}
    rebalance_band_pct: float = Field(5.0, gt=0)
    core_stop_pct: float = Field(35.0, gt=0, lt=100)
    base_currency: str = "CHF"

    @field_validator("core_targets")
    @classmethod
    def weights(cls, v: dict[str, float]) -> dict[str, float]:
        from tradedesk.universe import STABLES

        v = {k.strip().upper(): float(w) for k, w in v.items()}
        if cash := sorted(set(v) & STABLES):
            raise ValueError(f"core targets can't hold cash or stablecoins: {', '.join(cash)}")
        if any(w <= 0 for w in v.values()):
            raise ValueError("core target weights must be above 0")
        if v and abs(sum(v.values()) - 100) > 0.01:
            raise ValueError(f"core target weights add up to {sum(v.values()):g}, not 100")
        return v

    @model_validator(mode="after")
    def targets_when_on(self) -> "Portfolio":
        if self.core_pct > 0 and not self.core_targets:
            raise ValueError("core_pct is set but core_targets is empty")
        return self


class Settings(BaseModel):
    mode: Mode = Mode.PAPER
    market: Market = Market.SPOT
    quote: str = "USDT"
    watchlist: list[str] = ["BTC", "ETH", "SOL"]
    paper_equity: float = 1000.0
    risk: RiskLimits = RiskLimits()
    hold_days: HoldLimits = HoldLimits()
    execution: Execution = Execution()
    trailing: Trailing = Trailing()
    news_feeds: list[str] = [
        "https://www.coindesk.com/arc/outboundfeeds/rss/",
        "https://cointelegraph.com/rss",
        "https://decrypt.co/feed",
        "https://www.theblock.co/rss.xml",
    ]
    spot_url: str = ""
    futures_url: str = ""
    db_path: Path = Path("data/desk.db")
    runs_dir: Path = Path("runs")
    universe: Universe = Universe()
    notify: Notify = Notify()
    portfolio: Portfolio = Portfolio()
    # a second config for the futures wallet; one run then trades both
    futures_desk: Path | None = None
    transfers: Transfers = Transfers()
    gate: Gate = Gate()
    # the other dashboard (live or the paper lab), linked from the header
    peer_dashboard: str = ""

    @model_validator(mode="after")
    def core_not_quote(self) -> "Settings":
        if self.quote.upper() in self.portfolio.core_targets:
            raise ValueError(f"core targets can't hold the quote currency {self.quote}")
        return self

    def symbol(self, asset: str) -> str:
        return f"{asset.upper()}{self.quote}"

    def path(self, p: Path) -> Path:
        return p if p.is_absolute() else ROOT / p


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


@lru_cache
def settings() -> Settings:
    load_env(ROOT / ".env")
    return load(Path(os.environ.get("DESK_CONFIG", ROOT / "desk.toml")))


def load(path: Path) -> Settings:
    data = tomllib.loads(path.read_text()) if path.exists() else {}
    return Settings.model_validate(data)


def linked_settings(main: Settings) -> Settings | None:
    """The futures wallet's settings. Runs, mode and the confidence bar always follow the main
    desk, so one change in settings covers both wallets."""
    if main.futures_desk is None:
        return None
    if main.market is Market.FUTURES:
        raise ValueError("futures_desk needs the main desk on market = spot")
    s = load(main.path(main.futures_desk))
    risk = s.risk.model_copy(update={"min_confidence": main.risk.min_confidence})
    return s.model_copy(
        update={
            "risk": risk,
            "market": Market.FUTURES,
            "mode": main.mode,
            "runs_dir": main.runs_dir,
            "futures_desk": None,
            "watchlist": main.watchlist,
            "universe": main.universe,
        }
    )


def api_keys() -> tuple[str, str]:
    key = os.environ.get("BINANCE_API_KEY", "")
    secret = os.environ.get("BINANCE_API_SECRET", "")
    if not key or not secret:
        raise RuntimeError("BINANCE_API_KEY and BINANCE_API_SECRET must be set in .env")
    return key, secret
