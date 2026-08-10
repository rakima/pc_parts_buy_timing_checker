from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import messagebox

from victor.config import SettingsManager
from victor.database import VictorRepository
from victor.evaluator import BuyTimingEvaluator
from victor.fetchers import GenericHtmlPriceFetcher, PriceFetcherRegistry
from victor.gui import VictorApp
from victor.logging_config import configure_logging
from victor.services import PriceInvestigationService


def main() -> None:
    root_directory = Path(__file__).resolve().parent
    logger = configure_logging(root_directory / "logs")
    logger.info("アプリ起動")
    try:
        settings = SettingsManager(root_directory / "config" / "settings.json").load()
        repository = VictorRepository(root_directory / "data" / "victor.db")
        fetcher = GenericHtmlPriceFetcher(settings.user_agent, settings.request_timeout_seconds)
        registry = PriceFetcherRegistry(fetcher)
        evaluator = BuyTimingEvaluator(settings.evaluation)
        service = PriceInvestigationService(
            repository, registry, evaluator, settings.evaluation.comparison_days, logger
        )
        root = tk.Tk()
        VictorApp(root, repository, service, root_directory / "assets" / "images", logger)
        root.mainloop()
    except Exception as exc:
        logger.exception("例外")
        try:
            messagebox.showerror("起動エラー", str(exc))
        except tk.TclError:
            pass
        raise


if __name__ == "__main__":
    main()
