from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from victor.database import VictorRepository
from victor.models import PriceRecord, Product


class VictorRepositoryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = TemporaryDirectory()
        self.repository = VictorRepository(Path(self.temporary_directory.name) / "test.db")

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_product_crud_and_cascading_history_delete(self) -> None:
        product = self.repository.save_product(
            Product("テストGPU", "GPU", "https://example.com/gpu")
        )
        self.assertIsNotNone(product.id)
        product.name = "更新GPU"
        self.repository.save_product(product)
        self.assertEqual("更新GPU", self.repository.list_products()[0].name)
        self.assertEqual(product.id, self.repository.get_product_by_url(product.url).id)
        self.assertIsNone(self.repository.get_product_by_url("https://example.com/missing"))

        self.repository.add_price(PriceRecord(product.id or 0, 89_800, datetime(2026, 8, 10)))
        self.assertEqual(89_800, self.repository.get_price_history(product.id or 0)[0].price)

        self.repository.delete_product(product.id or 0)
        self.assertEqual([], self.repository.list_products())
        self.assertEqual([], self.repository.get_price_history(product.id or 0))


if __name__ == "__main__":
    unittest.main()
