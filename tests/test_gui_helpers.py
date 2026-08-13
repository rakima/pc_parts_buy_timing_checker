import unittest

from victor.gui import group_products_by_category, sort_product_candidates
from victor.models import Product, ProductCandidate


class GuiHelperTest(unittest.TestCase):
    def test_groups_products_by_category(self) -> None:
        products = [Product("SSD", "SSD", "u1"), Product("GPU", "GPU", "u2")]
        grouped = group_products_by_category(products)
        self.assertEqual(["GPU", "SSD"], [category for category, _items in grouped])

    def test_sorts_candidates_by_price_manufacturer_and_specs(self) -> None:
        products = [
            ProductCandidate("B", 200, "u1", "s", "GPU", manufacturer="ZOTAC",
                             specifications=(("容量", "8GB"),)),
            ProductCandidate("A", 100, "u2", "s", "GPU", manufacturer="ASUS",
                             specifications=(("容量", "12GB"),)),
        ]
        self.assertEqual([100, 200], [item.price for item in sort_product_candidates(products, "price")])
        self.assertEqual(["ASUS", "ZOTAC"], [item.manufacturer for item in
                         sort_product_candidates(products, "manufacturer")])
        self.assertEqual(["12GB", "8GB"], [item.specifications[0][1] for item in
                         sort_product_candidates(products, "specifications")])


if __name__ == "__main__":
    unittest.main()
