from __future__ import annotations

import html
import json
import re
import urllib.request
from abc import ABC, abstractmethod


class PriceFetchError(RuntimeError):
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
        request = urllib.request.Request(url, headers={"User-Agent": self.user_agent})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                charset = response.headers.get_content_charset() or "utf-8"
                content = response.read().decode(charset, errors="replace")
        except Exception as exc:
            raise PriceFetchError(f"ページを取得できませんでした: {exc}") from exc
        return self.extract_price(content)

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
        raise PriceFetchError("ページ内の構造化価格情報を見つけられませんでした")

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


class PriceFetcherRegistry:
    def __init__(self, default_fetcher: PriceFetcher) -> None:
        self.default_fetcher = default_fetcher
        self._fetchers: dict[str, PriceFetcher] = {}

    def register(self, site: str, fetcher: PriceFetcher) -> None:
        self._fetchers[site] = fetcher

    def get(self, site: str) -> PriceFetcher:
        return self._fetchers.get(site, self.default_fetcher)

