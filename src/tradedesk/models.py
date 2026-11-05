from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from tradedesk.config import Horizon


class Side(StrEnum):
    LONG = "long"
    SHORT = "short"

    @property
    def sign(self) -> int:
        return 1 if self is Side.LONG else -1


class Rating(StrEnum):
    BUY = "buy"
    OVERWEIGHT = "overweight"
    HOLD = "hold"
    UNDERWEIGHT = "underweight"
    SELL = "sell"


class PlanStatus(StrEnum):
    PROPOSED = "proposed"
    REJECTED = "rejected"
    APPROVED = "approved"
    PLACED = "placed"
    OPEN = "open"
    CLOSED = "closed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class TradeIdea(BaseModel):
    asset: str
    horizon: Horizon
    side: Side
    rating: Rating
    entry_type: Literal["limit", "market"] = "limit"
    entry: float = Field(gt=0)
    stop: float = Field(gt=0)
    take_profit: float = Field(gt=0)
    confidence: int = Field(ge=0, le=100)
    thesis: str = Field(max_length=400)
    invalidation: str = Field(max_length=200)
    # spot or futures when the desk trades both; auto sends shorts to futures, longs to spot
    venue: Literal["auto", "spot", "futures"] = "auto"

    @field_validator("asset")
    @classmethod
    def upper(cls, v: str) -> str:
        return v.strip().upper()

    @model_validator(mode="after")
    def levels_in_order(self) -> "TradeIdea":
        s = self.side.sign
        if (self.entry - self.stop) * s <= 0:
            raise ValueError("stop must be on the losing side of entry")
        if (self.take_profit - self.entry) * s <= 0:
            raise ValueError("take_profit must be on the winning side of entry")
        return self

    @property
    def reward_risk(self) -> float:
        return abs(self.take_profit - self.entry) / abs(self.entry - self.stop)


class PositionAction(BaseModel):
    position_id: int
    action: Literal["close", "tighten_stop"]
    stop: float | None = None
    reason: str = Field(max_length=200)
    venue: Literal["spot", "futures"] = "spot"


class PlanFile(BaseModel):
    market_view: str = Field(max_length=600)
    ideas: list[TradeIdea] = []
    position_actions: list[PositionAction] = []
