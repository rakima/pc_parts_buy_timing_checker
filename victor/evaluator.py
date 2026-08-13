from __future__ import annotations

from victor.config import EvaluationSettings
from collections import defaultdict
from datetime import timedelta
from statistics import pstdev

from victor.models import DailyPriceSummary, EvaluationResult, PriceRecord, TimingStatus


LABELS = {
    TimingStatus.WAITING: "指示待ち",
    TimingStatus.RESEARCHING: "調査中",
    TimingStatus.BAD: "時期が悪い",
    TimingStatus.INSUFFICIENT: "データ不足",
    TimingStatus.NEUTRAL: "微妙",
    TimingStatus.GOOD: "悪くない",
    TimingStatus.BUY: "買い時",
    TimingStatus.BEST_BUY: "絶好の買い時",
}

MESSAGES = {
    TimingStatus.WAITING: "ご指示をお待ちしております。何を調査しましょうか？",
    TimingStatus.RESEARCHING: "うーむ……データを確認しておる……",
    TimingStatus.BAD: "今は時期が悪い。待つのだ。",
    TimingStatus.INSUFFICIENT: "まだ判断材料が足りません。",
    TimingStatus.NEUTRAL: "悪くはないが……決め手に欠けるな。",
    TimingStatus.GOOD: "悪くない価格だ。検討する価値はある。",
    TimingStatus.BUY: "いいぞ。今は買い時だ。",
    TimingStatus.BEST_BUY: "素晴らしい！今こそ買うべき時だ！",
}


class BuyTimingEvaluator:
    def __init__(self, settings: EvaluationSettings) -> None:
        self.settings = settings

    def evaluate(self, current_price: int, history: list[PriceRecord],
                 stock_status: str | None = None) -> EvaluationResult:
        daily = self.summarize_daily(history)
        if stock_status in ("在庫なし", "販売終了"):
            return EvaluationResult(
                TimingStatus.INSUFFICIENT, LABELS[TimingStatus.INSUFFICIENT],
                "現在は購入できません。在庫の回復を待つのだ。", current_price,
                confidence_label="判定対象外",
            )
        if not self._has_enough_history(daily):
            return self._result(TimingStatus.INSUFFICIENT, current_price)

        filtered = self._exclude_outliers(daily)
        average = sum(item.average_price for item in filtered) / len(filtered)
        volatility = pstdev(item.average_price for item in filtered) / average * 100
        difference = ((current_price - average) / average) * 100
        status = self._status_for_difference(difference)
        latest_day = max(item.day for item in daily)
        recent = [item for item in daily if item.day >= latest_day - timedelta(days=6)]
        earlier = [item for item in daily if item.day < latest_day - timedelta(days=6)]
        seven_average = self._average_daily(recent)
        trend_percent = None
        trend_label = None
        if earlier and seven_average is not None:
            earlier_average = self._average_daily(earlier)
            assert earlier_average is not None
            trend_percent = ((seven_average - earlier_average) / earlier_average) * 100
            trend_label = "上昇" if trend_percent > 2 else "下落" if trend_percent < -2 else "横ばい"
        return EvaluationResult(
            status=status, label=LABELS[status], message=MESSAGES[status],
            current_price=current_price, average_price=average,
            difference_percent=difference,
            lowest_price=min(item.minimum_price for item in filtered),
            seven_day_average=seven_average, thirty_day_average=average,
            trend_percent=trend_percent, trend_label=trend_label,
            confidence_label=self._confidence(filtered, volatility),
            excluded_outlier_count=len(daily) - len(filtered),
            volatility_percent=volatility,
        )

    def _has_enough_history(self, history: list[DailyPriceSummary]) -> bool:
        if len(history) < self.settings.minimum_history_count:
            return False
        dates = [item.day for item in history]
        return (max(dates) - min(dates)).days >= self.settings.minimum_history_days

    @staticmethod
    def summarize_daily(history: list[PriceRecord]) -> list[DailyPriceSummary]:
        prices: dict[object, list[int]] = defaultdict(list)
        for item in history:
            prices[item.fetched_at.date()].append(item.price)
        return [DailyPriceSummary(day, min(values), sum(values) / len(values), len(values))
                for day, values in prices.items()]

    @staticmethod
    def _average_daily(summaries: list[DailyPriceSummary]) -> float | None:
        if not summaries:
            return None
        return sum(item.average_price for item in summaries) / len(summaries)

    @staticmethod
    def _exclude_outliers(summaries: list[DailyPriceSummary]) -> list[DailyPriceSummary]:
        if len(summaries) < 4:
            return summaries
        ordered = sorted(item.average_price for item in summaries)
        median = (ordered[(len(ordered) - 1) // 2] + ordered[len(ordered) // 2]) / 2
        deviations = sorted(abs(value - median) for value in ordered)
        mad = (deviations[(len(deviations) - 1) // 2] + deviations[len(deviations) // 2]) / 2
        if mad == 0:
            return [item for item in summaries if item.average_price == median] or summaries
        minimum, maximum = median - 3 * mad, median + 3 * mad
        return [item for item in summaries if minimum <= item.average_price <= maximum] or summaries

    @staticmethod
    def _confidence(summaries: list[DailyPriceSummary], volatility: float = 0) -> str:
        span = (max(item.day for item in summaries) - min(item.day for item in summaries)).days
        if volatility > 15:
            return "低（価格変動大）"
        if len(summaries) >= 14 and span >= 21:
            return "高"
        if len(summaries) >= 7 and span >= 14:
            return "中"
        return "低"

    def _status_for_difference(self, difference: float) -> TimingStatus:
        if difference >= self.settings.bad_percent:
            return TimingStatus.BAD
        if difference <= self.settings.best_buy_percent:
            return TimingStatus.BEST_BUY
        if difference <= self.settings.buy_percent:
            return TimingStatus.BUY
        if difference <= self.settings.good_percent:
            return TimingStatus.GOOD
        return TimingStatus.NEUTRAL

    @staticmethod
    def _result(status: TimingStatus, current: int, average: float | None = None,
                difference: float | None = None, lowest: int | None = None) -> EvaluationResult:
        return EvaluationResult(status, LABELS[status], MESSAGES[status], current,
                                average, difference, lowest)
