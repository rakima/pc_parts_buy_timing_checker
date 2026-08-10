from __future__ import annotations

from victor.config import EvaluationSettings
from victor.models import EvaluationResult, PriceRecord, TimingStatus


LABELS = {
    TimingStatus.RESEARCHING: "調査中",
    TimingStatus.BAD: "時期が悪い",
    TimingStatus.INSUFFICIENT: "データ不足",
    TimingStatus.NEUTRAL: "微妙",
    TimingStatus.GOOD: "悪くない",
    TimingStatus.BUY: "買い時",
    TimingStatus.BEST_BUY: "絶好の買い時",
}

MESSAGES = {
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

    def evaluate(self, current_price: int, history: list[PriceRecord]) -> EvaluationResult:
        if not self._has_enough_history(history):
            return self._result(TimingStatus.INSUFFICIENT, current_price)

        average = sum(item.price for item in history) / len(history)
        difference = ((current_price - average) / average) * 100
        status = self._status_for_difference(difference)
        return self._result(status, current_price, average, difference,
                            min(item.price for item in history))

    def _has_enough_history(self, history: list[PriceRecord]) -> bool:
        if len(history) < self.settings.minimum_history_count:
            return False
        dates = [item.fetched_at for item in history]
        return (max(dates) - min(dates)).days >= self.settings.minimum_history_days

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

