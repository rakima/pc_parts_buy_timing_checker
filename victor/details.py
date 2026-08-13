from __future__ import annotations

import html
import json
import re
import urllib.request
from abc import ABC, abstractmethod
from urllib.parse import urlparse

from victor.models import ProductDetail
from victor.fetch_errors import ParseFailure, classify_fetch_error


class ProductDetailFetchError(RuntimeError):
    pass


class ProductDetailFetcher(ABC):
    @abstractmethod
    def fetch(self, url: str) -> ProductDetail:
        pass


class StructuredProductDetailFetcher(ProductDetailFetcher):
    def __init__(self, user_agent: str, timeout_seconds: int = 15) -> None:
        self.user_agent = user_agent
        self.timeout_seconds = timeout_seconds

    def fetch(self, url: str) -> ProductDetail:
        self.validate_url(url)
        request = urllib.request.Request(url, headers={"User-Agent": self.user_agent})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                charset = response.headers.get_content_charset() or "utf-8"
                content = response.read().decode(charset, errors="replace")
        except Exception as exc:
            raise classify_fetch_error(exc, "商品詳細") from exc
        try:
            return self.parse(content)
        except ProductDetailFetchError as exc:
            raise ParseFailure(str(exc)) from exc

    def validate_url(self, url: str) -> None:
        del url

    @classmethod
    def parse(cls, content: str) -> ProductDetail:
        product = cls._product_json_ld(content)
        offers = product.get("offers") if isinstance(product.get("offers"), dict) else {}
        try:
            price = int(float(str(offers.get("price"))))
        except (TypeError, ValueError) as exc:
            raise ProductDetailFetchError("商品詳細の価格を解析できませんでした") from exc
        availability = str(offers.get("availability") or "")
        stock = cls._stock_label(availability, content)
        specs: list[tuple[str, str]] = []
        properties = product.get("additionalProperty", [])
        if isinstance(properties, list):
            for item in properties:
                if isinstance(item, dict) and item.get("name") and item.get("value"):
                    specs.append((str(item["name"]), str(item["value"])))
        for source_key, label in (("sku", "メーカー型番"), ("mpn", "メーカー型番"),
                                  ("gtin13", "JANコード"), ("gtin", "JANコード")):
            if product.get(source_key) and not any(key == label for key, _value in specs):
                specs.append((label, str(product[source_key])))
        brand = product.get("brand")
        if isinstance(brand, dict):
            brand = brand.get("name")
        if brand and not any(key == "メーカー" for key, _value in specs):
            specs.append(("メーカー", str(brand)))
        return ProductDetail(price, stock, tuple(specs))

    @staticmethod
    def _product_json_ld(content: str) -> dict[str, object]:
        for block in re.findall(
            r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
            html.unescape(content), re.I | re.S,
        ):
            try:
                value = json.loads(block.strip())
            except json.JSONDecodeError:
                continue
            values = value if isinstance(value, list) else [value]
            for item in values:
                if isinstance(item, dict) and item.get("@type") == "Product":
                    return item
        raise ProductDetailFetchError("商品詳細の構造化データが見つかりませんでした")

    @staticmethod
    def _stock_label(availability: str, content: str) -> str | None:
        mapping = {
            "InStock": "在庫あり", "LimitedAvailability": "在庫わずか",
            "OutOfStock": "在庫なし", "PreOrder": "予約受付中",
            "Discontinued": "販売終了",
        }
        for key, label in mapping.items():
            if key.lower() in availability.lower():
                return label
        match = re.search(r'"stkname"\s*:\s*"([^"]+)"', content)
        return match.group(1) if match else None


class TsukumoProductDetailFetcher(StructuredProductDetailFetcher):
    def validate_url(self, url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname != "shop.tsukumo.co.jp" or not re.fullmatch(r"/goods/\d+/?", parsed.path):
            raise ProductDetailFetchError("ツクモの商品URLではありません")


class DosparaProductDetailFetcher(StructuredProductDetailFetcher):
    def validate_url(self, url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname not in ("dospara.co.jp", "www.dospara.co.jp") or not re.fullmatch(r"/SBR\d+/IC\d+\.html", parsed.path):
            raise ProductDetailFetchError("ドスパラの商品URLではありません")

    @classmethod
    def parse(cls, content: str) -> ProductDetail:
        detail = super().parse(content)
        table = re.search(r'<caption>製品仕様</caption>(.*?)</table>', content, re.I | re.S)
        if not table:
            return detail
        specs = tuple(
            (cls._clean_cell(key), cls._clean_cell(value))
            for key, value in re.findall(r'<th[^>]*>(.*?)</th>\s*<td[^>]*>(.*?)</td>', table.group(1), re.I | re.S)
        )
        return ProductDetail(detail.price, detail.stock_status, specs)

    @staticmethod
    def _clean_cell(value: str) -> str:
        value = re.sub(r'<br\s*/?>', ' / ', value, flags=re.I)
        return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', html.unescape(value))).strip()


class ProductDetailFetcherRegistry:
    def __init__(self) -> None:
        self._fetchers: dict[str, ProductDetailFetcher] = {}

    def register(self, site: str, fetcher: ProductDetailFetcher) -> None:
        self._fetchers[site] = fetcher

    def get(self, site: str) -> ProductDetailFetcher:
        try:
            return self._fetchers[site]
        except KeyError as exc:
            raise ProductDetailFetchError(f"商品詳細未対応の店舗です: {site}") from exc
