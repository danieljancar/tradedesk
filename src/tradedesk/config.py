import os
import tomllib
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator

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
    min_reward_risk: float = Field(2.0, ge=1)
    daily_loss_limit_pct: float = Field(3.0, gt=0)
    max_drawdown_pct: float = Field(15.0, gt=0)
    min_stop_atr: float = Field(0.5, ge=0)
    max_stop_pct: float = Field(15.0, gt=0)
    min_confidence: int = Field(60, ge=0, le=100)
    max_entry_distance_pct: float = Field(8.0, gt=0)
    # House money: principal is risked at risk_per_trade_pct, profits above it at profit_risk_pct.
    principal: float | None = Field(None, gt=0)
    profit_risk_pct: float = Field(0.0, ge=0, le=25)
    # Share of the principal that open stops may never put at risk, all stops hit at once.
    floor_pct: float = Field(0.0, ge=0, le=100)
    # Futures: maintenance margin used to estimate the liquidation price (isolated margin).
    maintenance_margin_pct: float = Field(0.5, ge=0, le=10)


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


class Settings(BaseModel):
    mode: Mode = Mode.PAPER
    market: Market = Market.SPOT
    quote: str = "USDT"
    watchlist: list[str] = ["BTC", "ETH", "SOL"]
    paper_equity: float = 1000.0
    risk: RiskLimits = RiskLimits()
    hold_days: HoldLimits = HoldLimits()
    execution: Execution = Execution()
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
    notify: Notify = Notify()

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
    path = Path(os.environ.get("DESK_CONFIG", ROOT / "desk.toml"))
    data = tomllib.loads(path.read_text()) if path.exists() else {}
    return Settings.model_validate(data)


def api_keys() -> tuple[str, str]:
    key = os.environ.get("BINANCE_API_KEY", "")
    secret = os.environ.get("BINANCE_API_SECRET", "")
    if not key or not secret:
        raise RuntimeError("BINANCE_API_KEY and BINANCE_API_SECRET must be set in .env")
    return key, secret
