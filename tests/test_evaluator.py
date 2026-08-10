from datetime import datetime, timedelta
import unittest

from victor.config import EvaluationSettings
from victor.evaluator import BuyTimingEvaluator
from victor.models import PriceRecord, TimingStatus


class BuyTimingEvaluatorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.evaluator = BuyTimingEvaluator(EvaluationSettings())
        now = datetime(2026, 8, 10)
        self.history = [
            PriceRecord(1, 10_000, now - timedelta(days=day))
            for day in (1, 8, 15)
        ]

    def test_threshold_boundaries(self) -> None:
        cases = [
            (10_500, TimingStatus.BAD),
            (10_499, TimingStatus.NEUTRAL),
            (9_500, TimingStatus.GOOD),
            (9_000, TimingStatus.BUY),
            (8_500, TimingStatus.BEST_BUY),
        ]
        for price, expected in cases:
            with self.subTest(price=price):
                self.assertEqual(expected, self.evaluator.evaluate(price, self.history).status)

    def test_insufficient_when_count_is_too_low(self) -> None:
        result = self.evaluator.evaluate(9_000, self.history[:2])
        self.assertEqual(TimingStatus.INSUFFICIENT, result.status)

    def test_insufficient_when_period_is_too_short(self) -> None:
        now = datetime(2026, 8, 10)
        history = [PriceRecord(1, 10_000, now - timedelta(days=day)) for day in (1, 2, 3)]
        self.assertEqual(TimingStatus.INSUFFICIENT,
                         self.evaluator.evaluate(9_000, history).status)


if __name__ == "__main__":
    unittest.main()

