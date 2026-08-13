from __future__ import annotations

import html
import json
import re
import urllib.request
from abc import ABC, abstractmethod
from urllib.parse import urlparse
from victor.fetch_errors import ParseFailure, classify_fetch_error


class PriceFetchError(ParseFailure):
    pass


class PriceFetcher(ABC):
    @abstractmethod
    def fetch(self, url: str) -> int:
        """Return the current price in yen."""


class GenericHtmlPriceFetcher(PriceFetcher):
    """Extract a price from common structured metadata in an EC page."""

    META_PATTERNS = (
        re.compile(r'<meta[^>]+(?:property|name)=["\'](?:product:price:amount|og:price:amount)["\'][^>]+content=["\']([^"\']+)', re.I),
        re.compile(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\'](?:product:price:amount|og:price:amount)["\']', re.I),
    )

    def __init__(self, user_agent: str, timeout_seconds: int = 15) -> None:
        self.user_agent = user_agent
        self.timeout_seconds = timeout_seconds

    def fetch(self, url: str) -> int:
        content = self._download(url)
        return self.extract_price(content)

    def _download(self, url: str) -> str:
        request = urllib.request.Request(url, headers={"User-Agent": self.user_agent})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                charset = response.headers.get_content_charset() or "utf-8"
                return response.read().decode(charset, errors="replace")
        except Exception as exc:
            raise classify_fetch_error(exc, "商品ページ") from exc

    @classmethod
    def extract_price(cls, content: str) -> int:
        unescaped = html.unescape(content)
        for pattern in cls.META_PATTERNS:
            match = pattern.search(unescaped)
            if match:
                return cls._parse_price(match.group(1))

        for block in re.findall(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', unescaped, re.I | re.S):
            try:
                data = json.loads(block.strip())
            except json.JSONDecodeError:
                continue
            price = cls._find_json_price(data)
            if price is not None:
                return cls._parse_price(str(price))
        raise PriceFetchError("商品ページの価格構造が変更された可能性があります")

    @classmethod
    def _find_json_price(cls, value: object) -> object | None:
        if isinstance(value, dict):
            if "price" in value and isinstance(value["price"], (str, int, float)):
                return value["price"]
            for key in ("offers", "@graph", "mainEntity", "itemListElement"):
                if key in value:
                    found = cls._find_json_price(value[key])
                    if found is not None:
                        return found
        elif isinstance(value, list):
            for item in value:
                found = cls._find_json_price(item)
                if found is not None:
                    return found
        return None

    @staticmethod
    def _parse_price(value: str) -> int:
        normalized = re.sub(r"[^0-9.]", "", value.replace(",", ""))
        try:
            price = int(float(normalized))
        except (ValueError, OverflowError) as exc:
            raise PriceFetchError(f"価格を数値へ変換できませんでした: {value}") from exc
        if price < 0:
            raise PriceFetchError("価格が不正です")
        return price


class TsukumoPriceFetcher(GenericHtmlPriceFetcher):
    """Fetch a JPY price from a Tsukumo product detail page."""

    SITE_NAME = "ツクモ"
    HOST = "shop.tsukumo.co.jp"
    PRODUCT_PATH = re.compile(r"^/goods/\d+/?$")
    PRICE_META = re.compile(
        r'<meta[^>]+property=["\']product:price:amount["\'][^>]+content=["\']([^"\']+)',
        re.I,
    )
    CURRENCY_META = re.compile(
        r'<meta[^>]+property=["\']product:price:currency["\'][^>]+content=["\']([^"\']+)',
        re.I,
    )

    def fetch(self, url: str) -> int:
        self.validate_url(url)
        return self.extract_price(self._download(url))

    @classmethod
    def validate_url(cls, url: str) -> None:
        parsed = urlparse(url)
        if (parsed.scheme != "https" or parsed.hostname != cls.HOST
                or not cls.PRODUCT_PATH.fullmatch(parsed.path)):
            raise PriceFetchError(
                "ツクモの商品URL（https://shop.tsukumo.co.jp/goods/数字）を指定してください"
            )

    @classmethod
    def extract_price(cls, content: str) -> int:
        unescaped = html.unescape(content)
        currency = cls.CURRENCY_META.search(unescaped)
        price = cls.PRICE_META.search(unescaped)
        if currency and currency.group(1).upper() != "JPY":
            raise PriceFetchError(f"未対応の通貨です: {currency.group(1)}")
        if price:
            return cls._parse_price(price.group(1))
        return super().extract_price(unescaped)


class PriceFetcherRegistry:
    def __init__(self, default_fetcher: PriceFetcher) -> None:
        self.default_fetcher = default_fetcher
        self._fetchers: dict[str, PriceFetcher] = {}

    def register(self, site: str, fetcher: PriceFetcher) -> None:
        self._fetchers[site] = fetcher

    def get(self, site: str) -> PriceFetcher:
        return self._fetchers.get(site, self.default_fetcher)
