from __future__ import annotations

import html
import logging
import re
import time
import urllib.parse
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

from victor.fetch_errors import ParseFailure, classify_fetch_error
from victor.identity import normalize_identifier
from victor.models import ExternalPricePoint, PriceHistoryType, Product
from victor.normalization import normalize_product_name


class ExternalHistoryError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ExternalProductMatch:
    external_id: str
    name: str
    url: str
    match_method: str


class ExternalPriceHistoryProvider(ABC):
    provider_name: str

    @abstractmethod
    def find_product(self, product: Product) -> ExternalProductMatch | None:
        pass

    @abstractmethod
    def fetch_history(self, match: ExternalProductMatch) -> list[ExternalPricePoint]:
        pass


class KakakuPriceHistoryProvider(ExternalPriceHistoryProvider):
    provider_name = "KAKAKU"

    def __init__(self, user_agent: str, timeout_seconds: int = 15,
                 retry_count: int = 1, retry_interval_seconds: float = 1.0,
                 logger: logging.Logger | None = None) -> None:
        self.user_agent = user_agent
        self.timeout_seconds = timeout_seconds
        self.retry_count = retry_count
        self.retry_interval_seconds = retry_interval_seconds
        self.logger = logger or logging.getLogger("victor.external_history")

    def find_product(self, product: Product) -> ExternalProductMatch | None:
        query = product.model_number or product.name
        self.logger.info("価格.com商品検索開始 product=%s query=%s", product.name, query)
        content = self.fetch_page(
            f"https://search.kakaku.com/{urllib.parse.quote(query, safe='')}/"
        )
        candidates = self.parse_products(content)
        match = self.select_product(product, candidates)
        if match:
            self.logger.info("価格.com商品一致 product=%s external_id=%s method=%s",
                             product.name, match.external_id, match.match_method)
        else:
            self.logger.info("価格.com商品一致失敗 product=%s candidates=%s",
                             product.name, len(candidates))
        return match

    def fetch_history(self, match: ExternalProductMatch) -> list[ExternalPricePoint]:
        self.logger.info("価格.com履歴取得開始 external_id=%s", match.external_id)
        content = self.fetch_page(f"{match.url.rstrip('/')}/pricehistory/")
        points = self.parse_history(content, match.external_id)
        self.logger.info("価格.com履歴取得成功 external_id=%s count=%s",
                         match.external_id, len(points))
        return points

    def fetch_page(self, url: str) -> str:
        last_error: Exception | None = None
        for attempt in range(self.retry_count + 1):
            try:
                request = urllib.request.Request(url, headers={"User-Agent": self.user_agent})
                with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                    charset = response.headers.get_content_charset() or "utf-8"
                    raw = response.read()
                    decoded = raw.decode(charset, errors="replace")
                    cp932 = raw.decode("cp932", errors="replace")
                    return cp932 if cp932.count("\ufffd") < decoded.count("\ufffd") else decoded
            except Exception as exc:
                last_error = exc
                if attempt < self.retry_count:
                    time.sleep(self.retry_interval_seconds)
        assert last_error is not None
        raise classify_fetch_error(last_error, "価格.com") from last_error

    @classmethod
    def parse_products(cls, content: str) -> list[ExternalProductMatch]:
        names: dict[str, str] = {}
        pattern = re.compile(
            r'<a[^>]+href=["\'](?:https://kakaku\.com)?/item/(K\d+)/?["\'][^>]*>(.*?)</a>',
            re.I | re.S,
        )
        for external_id, label in pattern.findall(content):
            name = cls._clean(label)
            if name and len(name) > len(names.get(external_id, "")):
                names[external_id] = name
        return [ExternalProductMatch(item_id, name, f"https://kakaku.com/item/{item_id}/", "")
                for item_id, name in names.items()]

    @staticmethod
    def select_product(product: Product,
                       candidates: list[ExternalProductMatch]) -> ExternalProductMatch | None:
        model = normalize_identifier(product.model_number)
        if model:
            exact: list[ExternalProductMatch] = []
            maker_id = normalize_identifier(product.manufacturer)
            for candidate in candidates:
                title_without_specs = re.sub(r"\[[^\]]*\]", "", candidate.name)
                candidate_id = normalize_identifier(title_without_specs) or ""
                without_maker = candidate_id
                if maker_id and candidate_id.startswith(maker_id):
                    without_maker = candidate_id[len(maker_id):]
                if without_maker == model:
                    exact.append(candidate)
            model_matches = exact or [candidate for candidate in candidates
                                      if model in (normalize_identifier(candidate.name) or "")]
            if product.manufacturer and len(model_matches) > 1:
                maker = normalize_product_name(product.manufacturer)
                model_matches = [candidate for candidate in model_matches
                                 if maker in normalize_product_name(candidate.name)]
            if len(model_matches) == 1:
                candidate = model_matches[0]
                method = "manufacturer_model" if product.manufacturer else "model_exact"
                return ExternalProductMatch(candidate.external_id, candidate.name,
                                            candidate.url, method)
            return None
        target = normalize_product_name(product.name)
        exact = [candidate for candidate in candidates
                 if normalize_product_name(candidate.name) == target]
        if len(exact) == 1:
            candidate = exact[0]
            return ExternalProductMatch(candidate.external_id, candidate.name,
                                        candidate.url, "normalized_name")
        return None

    @classmethod
    def parse_history(cls, content: str, external_id: str) -> list[ExternalPricePoint]:
        points: list[ExternalPricePoint] = []
        for row in re.findall(r"<tr[^>]*>(.*?)</tr>", content, re.I | re.S):
            text = cls._clean(row)
            date_match = re.search(r"(20\d{2})年\s*(\d{1,2})月\s*(\d{1,2})日", text)
            price_match = re.search(r"[¥￥]\s*([\d,]+)", text)
            if not date_match or not price_match:
                continue
            try:
                observed = datetime(*map(int, date_match.groups()))
                price = int(price_match.group(1).replace(",", ""))
            except (ValueError, OverflowError):
                continue
            if price <= 0:
                continue
            points.append(ExternalPricePoint(
                cls.provider_name, external_id, price, observed,
                PriceHistoryType.MARKET_LOWEST, datetime.now(),
            ))
        if "日別の価格変動" in cls._clean(content) and not points:
            raise ParseFailure("価格.comの日別価格履歴を解析できませんでした")
        return sorted(points, key=lambda point: point.observed_at, reverse=True)[:30]

    @staticmethod
    def _clean(value: str) -> str:
        return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html.unescape(value))).strip()
