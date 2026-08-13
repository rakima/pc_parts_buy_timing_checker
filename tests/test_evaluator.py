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

    def test_uses_one_daily_average_per_day(self) -> None:
        now = datetime(2026, 8, 10)
        history = [
            PriceRecord(1, 8_000, now - timedelta(days=15)),
            PriceRecord(1, 12_000, now - timedelta(days=15, hours=-1)),
            PriceRecord(1, 10_000, now - timedelta(days=8)),
            PriceRecord(1, 10_000, now - timedelta(days=1)),
        ]
        result = self.evaluator.evaluate(10_000, history)
        self.assertEqual(10_000, result.thirty_day_average)

    def test_calculates_falling_short_term_trend(self) -> None:
        now = datetime(2026, 8, 10)
        history = [
            PriceRecord(1, 10_000, now - timedelta(days=15)),
            PriceRecord(1, 10_000, now - timedelta(days=8)),
            PriceRecord(1, 9_000, now - timedelta(days=6)),
            PriceRecord(1, 9_000, now - timedelta(days=1)),
        ]
        result = self.evaluator.evaluate(9_000, history)
        self.assertEqual(9_000, result.seven_day_average)
        self.assertEqual(-10.0, result.trend_percent)
        self.assertEqual("下落", result.trend_label)


if __name__ == "__main__":
    unittest.main()

