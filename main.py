from __future__ import annotations

import tkinter as tk
from datetime import datetime, timedelta
from pathlib import Path
from tkinter import messagebox

from victor.catalogs import (CachedCatalogFetcher, CatalogFetcherRegistry,
                             DosparaCatalogFetcher, SofmapCatalogFetcher,
                             TsukumoCatalogFetcher)
from victor.config import SettingsManager
from victor.database import VictorRepository
from victor.details import (DosparaProductDetailFetcher, ProductDetailFetcherRegistry,
                            SofmapProductDetailFetcher, TsukumoProductDetailFetcher)
from victor.evaluator import BuyTimingEvaluator
from victor.external_history import KakakuPriceHistoryProvider
from victor.fetchers import GenericHtmlPriceFetcher, PriceFetcherRegistry, TsukumoPriceFetcher
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
        deleted_cache = repository.purge_external_prices_before(
            datetime.now() - timedelta(days=settings.external_history_retention_days)
        )
        logger.info("外部価格履歴キャッシュ整理 deleted=%s retention_days=%s",
                    deleted_cache, settings.external_history_retention_days)
        fetcher = GenericHtmlPriceFetcher(settings.user_agent, settings.request_timeout_seconds)
        registry = PriceFetcherRegistry(fetcher)
        registry.register(
            TsukumoPriceFetcher.SITE_NAME,
            TsukumoPriceFetcher(settings.user_agent, settings.request_timeout_seconds),
        )
        catalogs = CatalogFetcherRegistry()
        catalogs.register(
            TsukumoCatalogFetcher.SITE_NAME,
            CachedCatalogFetcher(TsukumoCatalogFetcher(
                settings.user_agent, settings.request_timeout_seconds, logger
            )),
        )
        evaluator = BuyTimingEvaluator(settings.evaluation)
        details = ProductDetailFetcherRegistry()
        details.register("ツクモ", TsukumoProductDetailFetcher(
            settings.user_agent, settings.request_timeout_seconds
        ))
        details.register("ドスパラ", DosparaProductDetailFetcher(
            settings.user_agent, settings.request_timeout_seconds
        ))
        details.register("ソフマップ", SofmapProductDetailFetcher(
            settings.user_agent, settings.request_timeout_seconds
        ))
        service = PriceInvestigationService(
            repository, registry, details,
            KakakuPriceHistoryProvider(
                settings.user_agent, settings.request_timeout_seconds,
                settings.external_history_retry_count,
                settings.external_history_retry_interval_seconds, logger,
            ),
            evaluator, settings.evaluation.comparison_days, logger,
            settings.external_history_cache_hours,
            settings.external_history_minimum_points,
        )
        registry.register("ドスパラ", fetcher)
        catalogs.register(
            DosparaCatalogFetcher.SITE_NAME,
            CachedCatalogFetcher(DosparaCatalogFetcher(
                settings.user_agent, settings.request_timeout_seconds, logger
            )),
        )
        registry.register("ソフマップ", fetcher)
        catalogs.register(
            SofmapCatalogFetcher.SITE_NAME,
            CachedCatalogFetcher(SofmapCatalogFetcher(
                settings.user_agent, settings.request_timeout_seconds, logger
            )),
        )
        root = tk.Tk()
        VictorApp(root, repository, service, catalogs,
                  root_directory / "assets" / "images", logger)
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
