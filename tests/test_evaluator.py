from datetime import datetime, timedelta
import unittest

from victor.config import EvaluationSettings
from victor.evaluator import BuyTimingEvaluator
from victor.models import (EvaluationSource, ExternalPricePoint, PriceRecord,
                           TimingStatus)


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

    def test_excludes_extreme_daily_outlier(self) -> None:
        now = datetime(2026, 8, 10)
        history = [PriceRecord(1, price, now - timedelta(days=day)) for day, price in (
            (1, 10_000), (8, 10_000), (15, 10_000), (22, 100_000)
        )]
        result = self.evaluator.evaluate(10_000, history)
        self.assertEqual(10_000, result.thirty_day_average)
        self.assertEqual(1, result.excluded_outlier_count)

    def test_does_not_recommend_out_of_stock_product(self) -> None:
        result = self.evaluator.evaluate(1_000, self.history, "在庫なし")
        self.assertEqual(TimingStatus.INSUFFICIENT, result.status)
        self.assertEqual("判定対象外", result.confidence_label)

    def test_reduces_confidence_for_volatile_history(self) -> None:
        now = datetime(2026, 8, 10)
        history = [PriceRecord(1, price, now - timedelta(days=day)) for day, price in (
            (1, 7_000), (8, 10_000), (15, 13_000), (22, 10_000)
        )]
        result = self.evaluator.evaluate(9_000, history)
        self.assertEqual("低（価格変動大）", result.confidence_label)
        self.assertGreater(result.volatility_percent or 0, 15)

    def test_rejects_inconsistent_thresholds(self) -> None:
        with self.assertRaises(ValueError):
            EvaluationSettings(good_percent=-10, buy_percent=-5)

    def test_prefers_own_history_over_external_history(self) -> None:
        external = [ExternalPricePoint("KAKAKU", "K1", 20_000,
                    datetime(2026, 8, day)) for day in range(1, 6)]
        result = self.evaluator.evaluate(9_000, self.history, external_history=external)
        self.assertEqual(EvaluationSource.OWN_HISTORY, result.evaluation_source)
        self.assertEqual(10_000, result.average_price)

    def test_uses_external_history_when_own_history_is_insufficient(self) -> None:
        external = [ExternalPricePoint("KAKAKU", "K1", 10_000,
                    datetime(2026, 8, day)) for day in range(1, 6)]
        result = self.evaluator.evaluate(9_000, [], external_history=external)
        self.assertEqual(EvaluationSource.KAKAKU_MARKET_HISTORY, result.evaluation_source)
        self.assertEqual(TimingStatus.BUY, result.status)

    def test_reports_insufficient_source_when_both_histories_are_short(self) -> None:
        external = [ExternalPricePoint("KAKAKU", "K1", 10_000,
                    datetime(2026, 8, day)) for day in range(1, 5)]
        result = self.evaluator.evaluate(9_000, [], external_history=external)
        self.assertEqual(EvaluationSource.INSUFFICIENT_DATA, result.evaluation_source)

    def test_market_history_uses_same_threshold_boundaries(self) -> None:
        external = [ExternalPricePoint("KAKAKU", "K1", 10_000,
                    datetime(2026, 8, day)) for day in range(1, 6)]
        cases = ((10_500, TimingStatus.BAD), (10_499, TimingStatus.NEUTRAL),
                 (9_500, TimingStatus.GOOD), (9_000, TimingStatus.BUY),
                 (8_500, TimingStatus.BEST_BUY))
        for price, expected in cases:
            with self.subTest(price=price):
                result = self.evaluator.evaluate(price, [], external_history=external)
                self.assertEqual(expected, result.status)
                self.assertEqual(EvaluationSource.KAKAKU_MARKET_HISTORY,
                                 result.evaluation_source)


if __name__ == "__main__":
    unittest.main()

