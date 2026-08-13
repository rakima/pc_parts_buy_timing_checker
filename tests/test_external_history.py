import unittest

from victor.external_history import (ExternalProductMatch, KakakuPriceHistoryProvider)
from victor.fetch_errors import ParseFailure
from victor.models import Product


SEARCH_HTML = '''
<a href="https://kakaku.com/item/K0000000001/">MSI GeForce RTX 5070 12G VENTUS 2X OC [PCIExp 12GB]</a>
<a href="/item/K0000000002/">MSI GeForce RTX 5070 12G VENTUS 2X OC WHITE [PCIExp 12GB]</a>
'''


class KakakuPriceHistoryProviderTest(unittest.TestCase):
    def test_matches_exact_model(self) -> None:
        candidates = KakakuPriceHistoryProvider.parse_products(SEARCH_HTML)
        product = Product("GPU", "GPU", "url", manufacturer="MSI",
                          model_number="GeForce RTX 5070 12G VENTUS 2X OC")
        match = KakakuPriceHistoryProvider.select_product(product, candidates)
        self.assertEqual("K0000000001", match.external_id if match else None)

    def test_rejects_multiple_model_candidates(self) -> None:
        candidates = [ExternalProductMatch("K1", "MSI ABC-123", "u1", ""),
                      ExternalProductMatch("K2", "MSI ABC-123 WHITE", "u2", "")]
        product = Product("GPU", "GPU", "url", model_number="ABC-123")
        self.assertIsNone(KakakuPriceHistoryProvider.select_product(product, candidates))

    def test_matches_normalized_name_without_model(self) -> None:
        candidates = [ExternalProductMatch("K1", "MSI  GPU", "u", "")]
        product = Product("ＭＳＩ GPU", "GPU", "url")
        self.assertEqual("K1", KakakuPriceHistoryProvider.select_product(product, candidates).external_id)

    def test_returns_none_when_no_match(self) -> None:
        product = Product("different", "GPU", "url", model_number="XYZ-999")
        self.assertIsNone(KakakuPriceHistoryProvider.select_product(product, []))

    def test_parses_daily_history_and_ignores_invalid_price(self) -> None:
        rows = "".join(f"<tr><td>2026年 8月 {day}日</td><td>¥{90_000 + day:,}</td></tr>"
                       for day in range(1, 7))
        points = KakakuPriceHistoryProvider.parse_history(
            f"<h2>日別の価格変動</h2><table>{rows}<tr><td>2026年8月7日</td><td>価格なし</td></tr></table>", "K1")
        self.assertEqual(6, len(points))
        self.assertEqual("MARKET_LOWEST", points[0].price_type.value)

    def test_returns_empty_when_history_section_is_absent(self) -> None:
        self.assertEqual([], KakakuPriceHistoryProvider.parse_history("<html></html>", "K1"))

    def test_raises_when_history_structure_changed(self) -> None:
        with self.assertRaises(ParseFailure):
            KakakuPriceHistoryProvider.parse_history("<h2>日別の価格変動</h2>", "K1")


if __name__ == "__main__":
    unittest.main()
