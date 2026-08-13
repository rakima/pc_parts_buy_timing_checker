from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from collections.abc import Iterator

from victor.models import PriceRecord, Product


class VictorRepository:
    def __init__(self, database_path: Path) -> None:
        database_path.parent.mkdir(parents=True, exist_ok=True)
        self.database_path = database_path
        self.initialize()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS products (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    category TEXT NOT NULL,
                    url TEXT NOT NULL,
                    site TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    stock_status TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS price_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_id INTEGER NOT NULL,
                    price INTEGER NOT NULL CHECK(price >= 0),
                    fetched_at TEXT NOT NULL,
                    FOREIGN KEY(product_id) REFERENCES products(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_price_history_product_time
                    ON price_history(product_id, fetched_at);
                """
            )
            columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(products)")
            }
            if "stock_status" not in columns:
                connection.execute("ALTER TABLE products ADD COLUMN stock_status TEXT")

    def list_products(self) -> list[Product]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM products ORDER BY enabled DESC, name COLLATE NOCASE"
            ).fetchall()
        return [self._product_from_row(row) for row in rows]

    def get_product_by_url(self, url: str) -> Product | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM products WHERE url = ? LIMIT 1", (url,)
            ).fetchone()
        return self._product_from_row(row) if row else None

    def save_product(self, product: Product) -> Product:
        now = product.created_at or datetime.now()
        with self._connect() as connection:
            if product.id is None:
                cursor = connection.execute(
                    "INSERT INTO products(name, category, url, site, enabled, stock_status, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (product.name, product.category, product.url, product.site,
                     int(product.enabled), product.stock_status, now.isoformat()),
                )
                product.id = int(cursor.lastrowid)
                cursor.close()
                product.created_at = now
            else:
                connection.execute(
                    "UPDATE products SET name=?, category=?, url=?, site=?, enabled=?, stock_status=? WHERE id=?",
                    (product.name, product.category, product.url, product.site,
                     int(product.enabled), product.stock_status, product.id),
                )
        return product

    def delete_product(self, product_id: int) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM products WHERE id = ?", (product_id,))

    def add_price(self, record: PriceRecord) -> PriceRecord:
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO price_history(product_id, price, fetched_at) VALUES (?, ?, ?)",
                (record.product_id, record.price, record.fetched_at.isoformat()),
            )
            record_id = int(cursor.lastrowid)
            cursor.close()
        return PriceRecord(record.product_id, record.price, record.fetched_at, record_id)

    def get_prices_since(self, product_id: int, since: datetime) -> list[PriceRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM price_history WHERE product_id=? AND fetched_at>=? "
                "ORDER BY fetched_at DESC",
                (product_id, since.isoformat()),
            ).fetchall()
        return [self._price_from_row(row) for row in rows]

    def get_price_history(self, product_id: int, limit: int = 500) -> list[PriceRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM price_history WHERE product_id=? "
                "ORDER BY fetched_at DESC LIMIT ?", (product_id, limit)
            ).fetchall()
        return [self._price_from_row(row) for row in rows]

    @staticmethod
    def _product_from_row(row: sqlite3.Row) -> Product:
        return Product(id=row["id"], name=row["name"], category=row["category"],
                       url=row["url"], site=row["site"], enabled=bool(row["enabled"]),
                       stock_status=row["stock_status"],
                       created_at=datetime.fromisoformat(row["created_at"]))

    @staticmethod
    def _price_from_row(row: sqlite3.Row) -> PriceRecord:
        return PriceRecord(id=row["id"], product_id=row["product_id"], price=row["price"],
                           fetched_at=datetime.fromisoformat(row["fetched_at"]))
