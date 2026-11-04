import os
import tomllib
from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field

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


class Universe(BaseModel):
    enabled: bool = True
    min_quote_volume: float = Field(20_000_000, ge=0)
    top: int = Field(6, ge=0)
    max_assets: int = Field(12, ge=1)
    always: list[str] = []
    exclude: list[str] = []
    include_gold: bool = True


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
    universe: Universe = Universe()

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
