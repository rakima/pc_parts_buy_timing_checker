import unittest

from victor.fetchers import GenericHtmlPriceFetcher, PriceFetchError, TsukumoPriceFetcher


class GenericHtmlPriceFetcherTest(unittest.TestCase):
    def test_extracts_json_ld_price(self) -> None:
        content = '<script type="application/ld+json">{"offers":{"price":"89,800"}}</script>'
        self.assertEqual(89_800, GenericHtmlPriceFetcher.extract_price(content))

    def test_extracts_product_meta_price(self) -> None:
        content = '<meta property="product:price:amount" content="97420">'
        self.assertEqual(97_420, GenericHtmlPriceFetcher.extract_price(content))

    def test_raises_when_price_is_missing(self) -> None:
        with self.assertRaises(PriceFetchError):
            GenericHtmlPriceFetcher.extract_price("<html></html>")


class TsukumoPriceFetcherTest(unittest.TestCase):
    PRODUCT_URL = "https://shop.tsukumo.co.jp/goods/4251442513665"

    def test_extracts_jpy_product_meta_price(self) -> None:
        content = """
        <meta property="product:price:currency" content="JPY">
        <meta property="product:price:amount" content="12280">
        """
        self.assertEqual(12_280, TsukumoPriceFetcher.extract_price(content))

    def test_accepts_tsukumo_product_url(self) -> None:
        TsukumoPriceFetcher.validate_url(self.PRODUCT_URL)
        TsukumoPriceFetcher.validate_url(self.PRODUCT_URL + "/")

    def test_rejects_non_tsukumo_or_non_product_url(self) -> None:
        invalid_urls = (
            "http://shop.tsukumo.co.jp/goods/4251442513665",
            "https://example.com/goods/4251442513665",
            "https://shop.tsukumo.co.jp/parts",
        )
        for url in invalid_urls:
            with self.subTest(url=url), self.assertRaises(PriceFetchError):
                TsukumoPriceFetcher.validate_url(url)

    def test_rejects_non_jpy_price(self) -> None:
        content = """
        <meta property="product:price:currency" content="USD">
        <meta property="product:price:amount" content="100">
        """
        with self.assertRaises(PriceFetchError):
            TsukumoPriceFetcher.extract_price(content)


if __name__ == "__main__":
    unittest.main()
