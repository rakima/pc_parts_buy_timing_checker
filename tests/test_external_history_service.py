from datetime import datetime, timedelta
import logging
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from victor.config import EvaluationSettings
from victor.database import VictorRepository
from victor.evaluator import BuyTimingEvaluator
from victor.external_history import (ExternalPriceHistoryProvider, ExternalProductMatch)
from victor.models import ExternalPricePoint, Product
from victor.services import PriceInvestigationService


class _Provider(ExternalPriceHistoryProvider):
    provider_name = "KAKAKU"

    def __init__(self, fail: bool = False) -> None:
        self.fetch_count = 0
        self.fail = fail

    def find_product(self, product: Product) -> ExternalProductMatch | None:
        return ExternalProductMatch("K1", product.name, "https://kakaku.com/item/K1/", "model_exact")

    def fetch_history(self, match: ExternalProductMatch) -> list[ExternalPricePoint]:
        self.fetch_count += 1
        if self.fail:
            raise RuntimeError("network")
        now = datetime(2026, 8, 14)
        return [ExternalPricePoint("KAKAKU", match.external_id, 10_000,
                                  now - timedelta(days=day), fetched_at=now)
                for day in range(5)]


class ExternalHistoryServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = TemporaryDirectory()
        self.repository = VictorRepository(Path(self.temp.name) / "test.db")
        self.product = self.repository.save_product(
            Product("ABC-123", "GPU", "https://example.com", model_number="ABC-123")
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def service(self, provider: _Provider) -> PriceInvestigationService:
        return PriceInvestigationService(
            self.repository, None, None, provider,  # type: ignore[arg-type]
            BuyTimingEvaluator(EvaluationSettings()), 30, logging.getLogger("test"), 24, 5,
        )

    def test_reuses_cached_history(self) -> None:
        provider = _Provider()
        service = self.service(provider)
        now = datetime(2026, 8, 14)
        first = service._external_history(self.product, now, now - timedelta(days=30))
        second = service._external_history(self.product, now, now - timedelta(days=30))
        self.assertEqual(5, len(first))
        self.assertEqual(5, len(second))
        self.assertEqual(1, provider.fetch_count)

    def test_returns_empty_when_provider_fails(self) -> None:
        provider = _Provider(fail=True)
        result = self.service(provider)._external_history(
            self.product, datetime(2026, 8, 14), datetime(2026, 7, 15)
        )
        self.assertEqual([], result)


if __name__ == "__main__":
    unittest.main()
