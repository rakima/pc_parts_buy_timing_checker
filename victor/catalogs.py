from __future__ import annotations

import html
import logging
import re
import time
import urllib.request
from abc import ABC, abstractmethod
from datetime import datetime
from html.parser import HTMLParser
from typing import Callable

from victor.models import ProductCandidate
from victor.specifications import extract_specifications


class CatalogFetchError(RuntimeError):
    pass


class CatalogFetcher(ABC):
    @property
    @abstractmethod
    def supported_categories(self) -> tuple[str, ...]:
        pass

    @abstractmethod
    def fetch(self, category: str, page: int = 1) -> list[ProductCandidate]:
        """Return currently listed product candidates for one catalog page."""


class TsukumoCatalogFetcher(CatalogFetcher):
    SITE_NAME = "ツクモ"
    CATEGORY_PATHS = {
        "GPU": "/search/c20:2018/",
        "CPU": "/search/c20:2005/",
        "SSD": "/search/c20:2014:2014060/",
        "メモリ": "/search/c20:2010/",
    }

    def __init__(self, user_agent: str, timeout_seconds: int = 15,
                 logger: logging.Logger | None = None) -> None:
        self.user_agent = user_agent
        self.timeout_seconds = timeout_seconds
        self.logger = logger or logging.getLogger("victor.catalogs")

    @property
    def supported_categories(self) -> tuple[str, ...]:
        return tuple(self.CATEGORY_PATHS)

    def fetch(self, category: str, page: int = 1) -> list[ProductCandidate]:
        if category not in self.CATEGORY_PATHS:
            raise CatalogFetchError(f"ツクモの未対応カテゴリです: {category}")
        if page < 1:
            raise CatalogFetchError("ページ番号は1以上を指定してください")
        url = self._catalog_url(category, page)
        try:
            request = urllib.request.Request(url, headers={"User-Agent": self.user_agent})
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                charset = response.headers.get_content_charset() or "utf-8"
                content = response.read().decode(charset, errors="replace")
        except Exception as exc:
            raise CatalogFetchError(f"商品一覧を取得できませんでした: {exc}") from exc
        return self.parse_catalog(content, category, self.logger)

    def _catalog_url(self, category: str, page: int) -> str:
        path = self.CATEGORY_PATHS[category]
        if page > 1:
            path = f"{path.rstrip('/')}/p{page}/"
        return f"https://shop.tsukumo.co.jp{path}"

    @classmethod
    def parse_catalog(cls, content: str, category: str,
                      logger: logging.Logger | None = None) -> list[ProductCandidate]:
        parser = _TsukumoCatalogParser(category, logger or logging.getLogger("victor.catalogs"))
        try:
            parser.feed(content)
            parser.close()
        except Exception as exc:
            raise CatalogFetchError(f"商品一覧HTMLを解析できませんでした: {exc}") from exc
        return parser.candidates


class CachedCatalogFetcher(CatalogFetcher):
    def __init__(self, fetcher: CatalogFetcher, ttl_seconds: int = 300,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.fetcher = fetcher
        self.ttl_seconds = ttl_seconds
        self.clock = clock
        self.cache: dict[tuple[str, int], tuple[float, list[ProductCandidate]]] = {}

    @property
    def supported_categories(self) -> tuple[str, ...]:
        return self.fetcher.supported_categories

    def fetch(self, category: str, page: int = 1) -> list[ProductCandidate]:
        key = (category, page)
        now = self.clock()
        cached = self.cache.get(key)
        if cached and now - cached[0] < self.ttl_seconds:
            return list(cached[1])
        candidates = self.fetcher.fetch(category, page)
        self.cache[key] = (now, list(candidates))
        return candidates


class CatalogFetcherRegistry:
    def __init__(self) -> None:
        self._fetchers: dict[str, CatalogFetcher] = {}

    def register(self, shop: str, fetcher: CatalogFetcher) -> None:
        self._fetchers[shop] = fetcher

    def get(self, shop: str) -> CatalogFetcher:
        try:
            return self._fetchers[shop]
        except KeyError as exc:
            raise CatalogFetchError(f"未対応の店舗です: {shop}") from exc

    @property
    def shops(self) -> tuple[str, ...]:
        return tuple(self._fetchers)


class _TsukumoCatalogParser(HTMLParser):
    PRODUCT_CLASS = "search-box__product"

    def __init__(self, category: str, logger: logging.Logger) -> None:
        super().__init__(convert_charrefs=True)
        self.category = category
        self.logger = logger
        self.candidates: list[ProductCandidate] = []
        self.depth = 0
        self.data: dict[str, str] | None = None
        self.capture: str | None = None
        self.capture_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        classes = set((attributes.get("class") or "").split())
        if self.data is None:
            if tag == "div" and self.PRODUCT_CLASS in classes:
                self.data = {}
                self.depth = 1
            return

        if tag == "div":
            self.depth += 1
        if tag == "a" and "product-link" in classes and "url" not in self.data:
            self.data["url"] = attributes.get("href") or ""
        if tag == "a" and "maker_id" in (attributes.get("href") or ""):
            self._start_capture("manufacturer")
        elif tag == "h2" and "product-name" in classes:
            self._start_capture("name")
        elif tag == "div" and "search_stock_title" in classes:
            self._start_capture("stock_status")
        elif tag == "meta" and attributes.get("itemprop") == "price":
            self.data["price"] = attributes.get("content") or ""
        elif tag == "meta" and attributes.get("itemprop") == "description":
            self.data["description"] = attributes.get("content") or ""

    def handle_endtag(self, tag: str) -> None:
        if self.data is None:
            return
        if self.capture and self.depth == self.capture_depth:
            self.capture = None
        if tag == "div":
            self.depth -= 1
            if self.depth == 0:
                self._finish_product()

    def handle_data(self, data: str) -> None:
        if self.data is None or self.capture is None:
            return
        self.data[self.capture] = self.data.get(self.capture, "") + data

    def _start_capture(self, key: str) -> None:
        self.capture = key
        self.capture_depth = self.depth

    def _finish_product(self) -> None:
        assert self.data is not None
        try:
            name = self._clean(self.data.get("name", ""))
            url = self.data.get("url", "").strip()
            price = self._parse_price(self.data.get("price", ""))
            description = self._clean(self.data.get("description", ""))
            if not name or not re.fullmatch(r"https://shop\.tsukumo\.co\.jp/goods/\d+/", url):
                raise ValueError("商品名またはURLが不正です")
            self.candidates.append(ProductCandidate(
                name=name,
                price=price,
                url=url,
                shop=TsukumoCatalogFetcher.SITE_NAME,
                category=self.category,
                manufacturer=self._clean(self.data.get("manufacturer", "")) or None,
                stock_status=self._clean(self.data.get("stock_status", "")) or None,
                description=description or None,
                specifications=extract_specifications(self.category, name, description),
                fetched_at=datetime.now(),
            ))
        except ValueError as exc:
            self.logger.warning("商品解析失敗 data=%s error=%s", self.data, exc)
        finally:
            self.data = None
            self.capture = None
            self.depth = 0

    @staticmethod
    def _clean(value: str) -> str:
        return re.sub(r"\s+", " ", html.unescape(value)).strip()

    @staticmethod
    def _parse_price(value: str) -> int:
        normalized = re.sub(r"[^0-9]", "", html.unescape(value))
        if not normalized:
            raise ValueError(f"価格を数値へ変換できませんでした: {value}")
        return int(normalized)
