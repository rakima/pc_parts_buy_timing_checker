import unittest

from victor.fetchers import GenericHtmlPriceFetcher, PriceFetchError


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


if __name__ == "__main__":
    unittest.main()
