from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass(slots=True)
class EvaluationSettings:
    comparison_days: int = 30
    minimum_history_count: int = 3
    minimum_history_days: int = 7
    bad_percent: float = 5.0
    good_percent: float = -5.0
    buy_percent: float = -10.0
    best_buy_percent: float = -15.0

    def __post_init__(self) -> None:
        if not self.bad_percent > self.good_percent > self.buy_percent > self.best_buy_percent:
            raise ValueError("判定閾値は bad > good > buy > best_buy の順に指定してください")


@dataclass(slots=True)
class AppSettings:
    user_agent: str = "VictorPriceChecker/1.0 (manual desktop price check)"
    request_timeout_seconds: int = 15
    external_history_cache_hours: int = 24
    external_history_minimum_points: int = 5
    external_history_retry_count: int = 1
    external_history_retry_interval_seconds: float = 1.0
    external_history_retention_days: int = 90
    evaluation: EvaluationSettings = field(default_factory=EvaluationSettings)


class SettingsManager:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> AppSettings:
        if not self.path.exists():
            settings = AppSettings()
            self.save(settings)
            return settings
        data = json.loads(self.path.read_text(encoding="utf-8"))
        evaluation = EvaluationSettings(**data.pop("evaluation", {}))
        return AppSettings(evaluation=evaluation, **data)

    def save(self, settings: AppSettings) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(asdict(settings), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

