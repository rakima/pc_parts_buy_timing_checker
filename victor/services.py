from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable

from victor.database import VictorRepository
from victor.evaluator import BuyTimingEvaluator
from victor.fetchers import PriceFetcherRegistry
from victor.models import EvaluationResult, PriceRecord, Product


@dataclass(frozen=True, slots=True)
class InvestigationResult:
    product: Product
    evaluation: EvaluationResult
    fetched_at: datetime


class PriceInvestigationService:
    def __init__(self, repository: VictorRepository, fetchers: PriceFetcherRegistry,
                 evaluator: BuyTimingEvaluator, comparison_days: int,
                 logger: logging.Logger) -> None:
        self.repository = repository
        self.fetchers = fetchers
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
            current_price = self.fetchers.get(product.site).fetch(product.url)
            fetched_at = datetime.now()
            notify("過去価格と比較中...")
            since = fetched_at - timedelta(days=self.comparison_days)
            history = self.repository.get_prices_since(product.id, since)
            evaluation = self.evaluator.evaluate(current_price, history)
            self.repository.add_price(PriceRecord(product.id, current_price, fetched_at))
            self.logger.info("価格取得成功 product=%s price=%s", product.name, current_price)
            self.logger.info("判定結果 product=%s status=%s difference=%s",
                             product.name, evaluation.status, evaluation.difference_percent)
            return InvestigationResult(product, evaluation, fetched_at)
        except Exception:
            self.logger.exception("価格取得失敗 product=%s url=%s fetched_at=%s",
                                  product.name, product.url, datetime.now().isoformat())
            raise

