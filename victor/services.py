from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable

from victor.database import VictorRepository
from victor.details import ProductDetailFetcherRegistry
from victor.evaluator import BuyTimingEvaluator
from victor.fetchers import PriceFetcherRegistry
from victor.fetch_errors import ProductUnavailableFailure
from victor.identity import identify_candidate
from victor.models import (EvaluationResult, InventoryRecord, PriceRecord, Product,
                           ProductCandidate)


@dataclass(frozen=True, slots=True)
class InvestigationResult:
    product: Product
    evaluation: EvaluationResult
    fetched_at: datetime


class PriceInvestigationService:
    def __init__(self, repository: VictorRepository, fetchers: PriceFetcherRegistry,
                 detail_fetchers: ProductDetailFetcherRegistry,
                 evaluator: BuyTimingEvaluator, comparison_days: int,
                 logger: logging.Logger) -> None:
        self.repository = repository
        self.fetchers = fetchers
        self.detail_fetchers = detail_fetchers
        self.evaluator = evaluator
        self.comparison_days = comparison_days
        self.logger = logger

    def investigate(self, product: Product,
                    progress: Callable[[str], None] | None = None) -> InvestigationResult:
        if product.id is None:
            raise ValueError("未登録の商品は調査できません")
        if not product.enabled:
            raise ValueError("無効な商品は調査できません")

        notify = progress or (lambda _message: None)
        self.logger.info("価格取得開始 product=%s url=%s", product.name, product.url)
        notify(f"{product.site}を確認中...")
        try:
            try:
                detail = self.detail_fetchers.get(product.site).fetch(product.url)
                current_price = detail.price
                product.stock_status = detail.stock_status
                if detail.specifications:
                    product.specifications = detail.specifications
                identity = identify_candidate(ProductCandidate(
                    product.name, detail.price, product.url, product.site, product.category,
                    manufacturer=product.manufacturer, model_name=product.model_number,
                    specifications=product.specifications,
                ))
                product.manufacturer = product.manufacturer or identity.manufacturer
                product.model_number = identity.model_number or product.model_number
                product.jan_code = identity.jan_code or product.jan_code
                self.repository.save_product(product)
            except ProductUnavailableFailure:
                product.stock_status = "販売終了"
                self.repository.save_product(product)
                self.repository.add_inventory(
                    InventoryRecord(product.id, "販売終了", datetime.now())
                )
                raise
            except Exception:
                self.logger.exception("商品詳細取得失敗、価格取得へフォールバック product=%s", product.name)
                current_price = self.fetchers.get(product.site).fetch(product.url)
                detail = None
            fetched_at = datetime.now()
            notify("過去価格と比較中...")
            since = fetched_at - timedelta(days=self.comparison_days)
            history = self.repository.get_prices_since(product.id, since)
            evaluation = self.evaluator.evaluate(current_price, history, product.stock_status)
            self.repository.add_price(PriceRecord(product.id, current_price, fetched_at))
            if detail and detail.stock_status:
                self.repository.add_inventory(
                    InventoryRecord(product.id, detail.stock_status, fetched_at)
                )
            self.logger.info("価格取得成功 product=%s price=%s", product.name, current_price)
            self.logger.info("判定結果 product=%s status=%s difference=%s",
                             product.name, evaluation.status, evaluation.difference_percent)
            return InvestigationResult(product, evaluation, fetched_at)
        except Exception:
            self.logger.exception("価格取得失敗 product=%s url=%s fetched_at=%s",
                                  product.name, product.url, datetime.now().isoformat())
            raise

