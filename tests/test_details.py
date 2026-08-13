import unittest

from victor.details import DosparaProductDetailFetcher, TsukumoProductDetailFetcher


class ProductDetailFetcherTest(unittest.TestCase):
    def test_parses_tsukumo_specs_and_limited_stock(self) -> None:
        html = '''<script type="application/ld+json">{"@type":"Product","additionalProperty":[{"name":"搭載メモリ","value":"8GB GDDR6"}],"offers":{"price":54980,"availability":"https://schema.org/LimitedAvailability"}}</script>'''
        detail = TsukumoProductDetailFetcher.parse(html)
        self.assertEqual(54_980, detail.price)
        self.assertEqual("在庫わずか", detail.stock_status)
        self.assertEqual((("搭載メモリ", "8GB GDDR6"),), detail.specifications)

    def test_parses_dospara_out_of_stock(self) -> None:
        html = '''<script type="application/ld+json">{"@type":"Product","offers":{"price":"122800","availability":"http://schema.org/OutOfStock"}}</script><table><caption>製品仕様</caption><tr><th>メモリ容量</th><td>12GB</td></tr></table>'''
        detail = DosparaProductDetailFetcher.parse(html)
        self.assertEqual(122_800, detail.price)
        self.assertEqual("在庫なし", detail.stock_status)
        self.assertEqual((("メモリ容量", "12GB"),), detail.specifications)

    def test_extracts_identity_fields_from_structured_detail(self) -> None:
        html = '''<script type="application/ld+json">{
          "@type":"Product", "sku":"ABC-123", "gtin13":"4988755000000",
          "brand":{"name":"MSI"}, "offers":{"price":"89800","availability":"InStock"}
        }</script>'''
        detail = TsukumoProductDetailFetcher.parse(html)
        self.assertIn(("メーカー型番", "ABC-123"), detail.specifications)
        self.assertIn(("JANコード", "4988755000000"), detail.specifications)
        self.assertIn(("メーカー", "MSI"), detail.specifications)


if __name__ == "__main__":
    unittest.main()
