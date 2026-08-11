from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class TimingStatus(StrEnum):
    WAITING = "waiting"
    RESEARCHING = "researching"
    BAD = "bad"
    INSUFFICIENT = "insufficient"
    NEUTRAL = "neutral"
    GOOD = "good"
    BUY = "buy"
    BEST_BUY = "best_buy"


@dataclass(slots=True)
class Product:
    name: str
    category: str
    url: str
    site: str = "汎用ECサイト"
    enabled: bool = True
    id: int | None = None
    created_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class ProductCandidate:
    name: str
    price: int
    url: str
    shop: str
    category: str
    manufacturer: str | None = None
    model_name: str | None = None
    stock_status: str | None = None
    fetched_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class PriceRecord:
    product_id: int
    price: int
    fetched_at: datetime
    id: int | None = None


@dataclass(frozen=True, slots=True)
class EvaluationResult:
    status: TimingStatus
    label: str
    message: str
    current_price: int
    average_price: float | None = None
    difference_percent: float | None = None
    lowest_price: int | None = None
