from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable

from victor.database import VictorRepository
from victor.details import ProductDetailFetcherRegistry
from victor.evaluator import BuyTimingEvaluator
from victor.external_history import (ExternalPriceHistoryProvider, ExternalProductMatch)
from victor.fetchers import PriceFetcherRegistry
from victor.fetch_errors import ProductUnavailableFailure
from victor.identity import identify_candidate
from victor.models import (EvaluationResult, InventoryRecord, PriceRecord, Product,
                           ProductCandidate, ExternalProductMapping, ExternalPricePoint)


@dataclass(frozen=True, slots=True)
class InvestigationResult:
    product: Product
    evaluation: EvaluationResult
    fetched_at: datetime


class PriceInvestigationService:
    def __init__(self, repository: VictorRepository, fetchers: PriceFetcherRegistry,
                 detail_fetchers: ProductDetailFetcherRegistry,
                 external_history_provider: ExternalPriceHistoryProvider,
                 evaluator: BuyTimingEvaluator, comparison_days: int,
                 logger: logging.Logger, external_cache_hours: int = 24,
                 external_minimum_points: int = 5) -> None:
        self.repository = repository
        self.fetchers = fetchers
        self.detail_fetchers = detail_fetchers
        self.external_history_provider = external_history_provider
        self.evaluator = evaluator
        self.comparison_days = comparison_days
        self.logger = logger
        self.external_cache_hours = external_cache_hours
        self.external_minimum_points = external_minimum_points

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
            external_history: list[ExternalPricePoint] = []
            if not self.evaluator.has_sufficient_history(history):
                notify("価格.comの市場価格を確認中...")
                external_history = self._external_history(product, fetched_at, since)
            evaluation = self.evaluator.evaluate(
                current_price, history, product.stock_status, external_history,
                self.external_minimum_points,
            )
            if external_history and evaluation.evaluation_source.value == "KAKAKU_MARKET_HISTORY":
                self.logger.info("外部履歴判定使用 product=%s count=%s", product.name,
                                 len(external_history))
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

    def _external_history(self, product: Product, now: datetime,
                          since: datetime) -> list[ExternalPricePoint]:
        assert product.id is not None
        provider = self.external_history_provider
        try:
            mapping = self.repository.get_external_mapping(product.id, provider.provider_name)
            if mapping:
                match = ExternalProductMatch(mapping.external_id, product.name,
                                             mapping.external_url, mapping.match_method)
            else:
                match = provider.find_product(product)
                if not match:
                    return []
                self.repository.save_external_mapping(ExternalProductMapping(
                    product.id, provider.provider_name, match.external_id, match.url,
                    match.match_method, now,
                ))
            cached = self.repository.get_external_prices(provider.provider_name,
                                                         match.external_id, since)
            newest_fetch = max((point.fetched_at for point in cached if point.fetched_at),
                               default=None)
            if newest_fetch and newest_fetch >= now - timedelta(hours=self.external_cache_hours):
                self.logger.info("キャッシュ利用 provider=%s external_id=%s count=%s",
                                 provider.provider_name, match.external_id, len(cached))
                return cached
            fetched = provider.fetch_history(match)
            self.repository.save_external_prices(fetched)
            return fetched
        except Exception:
            self.logger.exception("価格.com履歴取得失敗 product=%s", product.name)
            return []

