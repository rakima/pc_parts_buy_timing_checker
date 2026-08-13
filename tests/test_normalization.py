import unittest

from victor.normalization import matches_product_name, normalize_product_name


class ProductNameNormalizationTest(unittest.TestCase):
    def test_normalizes_width_case_and_whitespace(self) -> None:
        self.assertEqual("msi rtx 5070 ti", normalize_product_name(" ＭＳＩ  RTX  5070 Ti "))

    def test_matches_name_locally_by_partial_text(self) -> None:
        name = "MSI GeForce RTX 5070 Ti GAMING OC 16G"
        self.assertTrue(matches_product_name(name, "rtx 5070"))
        self.assertFalse(matches_product_name(name, "RX 9070"))


if __name__ == "__main__":
    unittest.main()
