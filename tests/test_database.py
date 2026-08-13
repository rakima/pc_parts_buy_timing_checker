from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
import sqlite3
from contextlib import closing
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
            Product("テストGPU", "GPU", "https://example.com/gpu", stock_status="在庫あり")
        )
        self.assertIsNotNone(product.id)
        product.name = "更新GPU"
        self.repository.save_product(product)
        self.assertEqual("更新GPU", self.repository.list_products()[0].name)
        self.assertEqual("在庫あり", self.repository.list_products()[0].stock_status)
        self.assertEqual(product.id, self.repository.get_product_by_url(product.url).id)
        self.assertIsNone(self.repository.get_product_by_url("https://example.com/missing"))

        self.repository.add_price(PriceRecord(product.id or 0, 89_800, datetime(2026, 8, 10)))
        self.assertEqual(89_800, self.repository.get_price_history(product.id or 0)[0].price)

        self.repository.delete_product(product.id or 0)
        self.assertEqual([], self.repository.list_products())
        self.assertEqual([], self.repository.get_price_history(product.id or 0))

    def test_adds_stock_column_to_existing_database(self) -> None:
        legacy_path = Path(self.temporary_directory.name) / "legacy.db"
        with closing(sqlite3.connect(legacy_path)) as connection:
            cursor = connection.execute(
                "CREATE TABLE products (id INTEGER PRIMARY KEY, name TEXT NOT NULL, "
                "category TEXT NOT NULL, url TEXT NOT NULL, site TEXT NOT NULL, "
                "enabled INTEGER NOT NULL, created_at TEXT NOT NULL)"
            )
            cursor.close()
            connection.commit()
        VictorRepository(legacy_path)
        with closing(sqlite3.connect(legacy_path)) as connection:
            cursor = connection.execute("PRAGMA table_info(products)")
            columns = {row[1] for row in cursor.fetchall()}
            cursor.close()
        self.assertIn("stock_status", columns)


if __name__ == "__main__":
    unittest.main()
