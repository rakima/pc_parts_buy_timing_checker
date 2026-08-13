from __future__ import annotations

import unittest

from victor.catalogs import CachedCatalogFetcher, CatalogFetcher, TsukumoCatalogFetcher
from victor.models import ProductCandidate


CATALOG_FIXTURE = """
<div class="search-box__product">
  <a class="product-link" href="https://shop.tsukumo.co.jp/goods/1111111111111/">
    <img alt="GPU">
  </a>
  <span class="search-box__product-name">
    <a href="/search/c20:2018/p1/?maker_id[]=123">MSI エムエスアイ</a>
    <a class="product-link" href="https://shop.tsukumo.co.jp/goods/1111111111111/">
      <h2 class="product-name">GeForce RTX 5070 Ti 16G</h2>
    </a>
  </span>
  <div class="search_stock_title"><span>在庫わずか</span><span>24時間以内</span>に出荷</div>
  <meta itemprop="priceCurrency" content="JPY">
  <meta itemprop="price" content="&yen;149,800(税込)">
</div>
<div class="search-box__product">
  <a class="product-link" href="https://shop.tsukumo.co.jp/goods/2222222222222/">
    <h2 class="product-name">価格不明GPU</h2>
  </a>
  <meta itemprop="price" content="価格未定">
</div>
"""


class TsukumoCatalogFetcherTest(unittest.TestCase):
    def test_parses_valid_cards_and_skips_invalid_cards(self) -> None:
        candidates = TsukumoCatalogFetcher.parse_catalog(CATALOG_FIXTURE, "GPU")
        self.assertEqual(1, len(candidates))
        candidate = candidates[0]
        self.assertIsInstance(candidate, ProductCandidate)
        self.assertEqual("GeForce RTX 5070 Ti 16G", candidate.name)
        self.assertEqual(149_800, candidate.price)
        self.assertEqual("ツクモ", candidate.shop)
        self.assertEqual("GPU", candidate.category)
        self.assertEqual("MSI エムエスアイ", candidate.manufacturer)
        self.assertEqual("在庫わずか", candidate.stock_status)
        self.assertIsNotNone(candidate.fetched_at)

    def test_builds_first_and_later_page_urls(self) -> None:
        fetcher = TsukumoCatalogFetcher("test")
        self.assertEqual(
            "https://shop.tsukumo.co.jp/search/c20:2018/",
            fetcher._catalog_url("GPU", 1),
        )
        self.assertEqual(
            "https://shop.tsukumo.co.jp/search/c20:2018/p2/",
            fetcher._catalog_url("GPU", 2),
        )


class _CountingCatalogFetcher(CatalogFetcher):
    def __init__(self) -> None:
        self.calls = 0

    @property
    def supported_categories(self) -> tuple[str, ...]:
        return ("GPU",)

    def fetch(self, category: str, page: int = 1) -> list[ProductCandidate]:
        self.calls += 1
        return [ProductCandidate("GPU", 10_000, "https://example.com/1", "shop", category)]


class CachedCatalogFetcherTest(unittest.TestCase):
    def test_uses_cached_candidates_until_ttl_expires(self) -> None:
        current_time = [100.0]
        source = _CountingCatalogFetcher()
        fetcher = CachedCatalogFetcher(source, ttl_seconds=300, clock=lambda: current_time[0])
        fetcher.fetch("GPU")
        fetcher.fetch("GPU")
        self.assertEqual(1, source.calls)
        current_time[0] += 301
        fetcher.fetch("GPU")
        self.assertEqual(2, source.calls)


if __name__ == "__main__":
    unittest.main()
