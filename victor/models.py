from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
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


class EvaluationSource(StrEnum):
    OWN_HISTORY = "OWN_HISTORY"
    KAKAKU_MARKET_HISTORY = "KAKAKU_MARKET_HISTORY"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class PriceHistoryType(StrEnum):
    MARKET_LOWEST = "MARKET_LOWEST"


@dataclass(slots=True)
class Product:
    name: str
    category: str
    url: str
    site: str = "汎用ECサイト"
    enabled: bool = True
    stock_status: str | None = None
    specifications: tuple[tuple[str, str], ...] = ()
    manufacturer: str | None = None
    model_number: str | None = None
    jan_code: str | None = None
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
    description: str | None = None
    specifications: tuple[tuple[str, str], ...] = ()
    fetched_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class PriceRecord:
    product_id: int
    price: int
    fetched_at: datetime
    id: int | None = None


@dataclass(frozen=True, slots=True)
class InventoryRecord:
    product_id: int
    stock_status: str
    fetched_at: datetime
    id: int | None = None


@dataclass(frozen=True, slots=True)
class ProductDetail:
    price: int
    stock_status: str | None
    specifications: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class ProductIdentity:
    manufacturer: str | None
    model_number: str | None
    jan_code: str | None


@dataclass(frozen=True, slots=True)
class ProductMatch:
    candidate: ProductCandidate
    confidence: str
    reason: str


@dataclass(frozen=True, slots=True)
class ExternalProductMapping:
    product_id: int
    provider: str
    external_id: str
    external_url: str
    match_method: str
    matched_at: datetime


@dataclass(frozen=True, slots=True)
class ExternalPricePoint:
    provider: str
    external_product_id: str
    price: int
    observed_at: datetime
    price_type: PriceHistoryType = PriceHistoryType.MARKET_LOWEST
    fetched_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class DailyPriceSummary:
    day: date
    minimum_price: int
    average_price: float
    sample_count: int


@dataclass(frozen=True, slots=True)
class EvaluationResult:
    status: TimingStatus
    label: str
    message: str
    current_price: int
    average_price: float | None = None
    difference_percent: float | None = None
    lowest_price: int | None = None
    seven_day_average: float | None = None
    thirty_day_average: float | None = None
    trend_percent: float | None = None
    trend_label: str | None = None
    confidence_label: str | None = None
    excluded_outlier_count: int = 0
    volatility_percent: float | None = None
    evaluation_source: EvaluationSource = EvaluationSource.INSUFFICIENT_DATA
