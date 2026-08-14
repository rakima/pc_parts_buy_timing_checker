from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from collections.abc import Iterator

from victor.models import (DailyPriceSummary, ExternalPricePoint, ExternalProductMapping,
                           InventoryRecord, PriceHistoryType, PriceRecord, Product)


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
                    specifications_json TEXT NOT NULL DEFAULT '[]',
                    manufacturer TEXT,
                    model_number TEXT,
                    jan_code TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS price_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_id INTEGER NOT NULL,
                    price INTEGER NOT NULL CHECK(price >= 0),
                    fetched_at TEXT NOT NULL,
                    FOREIGN KEY(product_id) REFERENCES products(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS inventory_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_id INTEGER NOT NULL,
                    stock_status TEXT NOT NULL,
                    fetched_at TEXT NOT NULL,
                    FOREIGN KEY(product_id) REFERENCES products(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_price_history_product_time
                    ON price_history(product_id, fetched_at);
                CREATE TABLE IF NOT EXISTS product_external_mappings (
                    product_id INTEGER NOT NULL,
                    provider TEXT NOT NULL,
                    external_id TEXT NOT NULL,
                    external_url TEXT NOT NULL,
                    match_method TEXT NOT NULL,
                    matched_at TEXT NOT NULL,
                    PRIMARY KEY(product_id, provider),
                    FOREIGN KEY(product_id) REFERENCES products(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS external_price_history (
                    provider TEXT NOT NULL,
                    external_product_id TEXT NOT NULL,
                    price INTEGER NOT NULL CHECK(price >= 0),
                    observed_at TEXT NOT NULL,
                    price_type TEXT NOT NULL,
                    fetched_at TEXT NOT NULL,
                    PRIMARY KEY(provider, external_product_id, observed_at, price_type)
                );
                CREATE INDEX IF NOT EXISTS idx_external_history_product_time
                    ON external_price_history(provider, external_product_id, fetched_at);
                CREATE TABLE IF NOT EXISTS external_provider_status (
                    product_id INTEGER NOT NULL,
                    provider TEXT NOT NULL,
                    status TEXT NOT NULL,
                    message TEXT NOT NULL,
                    item_count INTEGER NOT NULL DEFAULT 0,
                    checked_at TEXT NOT NULL,
                    PRIMARY KEY(product_id, provider),
                    FOREIGN KEY(product_id) REFERENCES products(id) ON DELETE CASCADE
                );
                """
            )
            cursor = connection.execute("PRAGMA table_info(products)")
            columns = {row["name"] for row in cursor.fetchall()}
            cursor.close()
            if "stock_status" not in columns:
                connection.execute("ALTER TABLE products ADD COLUMN stock_status TEXT")
            if "specifications_json" not in columns:
                connection.execute(
                    "ALTER TABLE products ADD COLUMN specifications_json TEXT NOT NULL DEFAULT '[]'"
                )
            for column in ("manufacturer", "model_number", "jan_code"):
                if column not in columns:
                    connection.execute(f"ALTER TABLE products ADD COLUMN {column} TEXT")

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
                    "INSERT INTO products(name, category, url, site, enabled, stock_status, "
                    "specifications_json, manufacturer, model_number, jan_code, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (product.name, product.category, product.url, product.site,
                     int(product.enabled), product.stock_status,
                     json.dumps(product.specifications, ensure_ascii=False), product.manufacturer,
                     product.model_number, product.jan_code, now.isoformat()),
                )
                product.id = int(cursor.lastrowid)
                cursor.close()
                product.created_at = now
            else:
                connection.execute(
                    "UPDATE products SET name=?, category=?, url=?, site=?, enabled=?, stock_status=?, "
                    "specifications_json=?, manufacturer=?, model_number=?, jan_code=? WHERE id=?",
                    (product.name, product.category, product.url, product.site,
                     int(product.enabled), product.stock_status,
                     json.dumps(product.specifications, ensure_ascii=False), product.manufacturer,
                     product.model_number, product.jan_code, product.id),
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

    def add_inventory(self, record: InventoryRecord) -> InventoryRecord:
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO inventory_history(product_id, stock_status, fetched_at) VALUES (?, ?, ?)",
                (record.product_id, record.stock_status, record.fetched_at.isoformat()),
            )
            record_id = int(cursor.lastrowid)
            cursor.close()
        return InventoryRecord(record.product_id, record.stock_status, record.fetched_at, record_id)

    def get_inventory_history(self, product_id: int, limit: int = 100) -> list[InventoryRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM inventory_history WHERE product_id=? ORDER BY fetched_at DESC LIMIT ?",
                (product_id, limit),
            ).fetchall()
        return [InventoryRecord(row["product_id"], row["stock_status"],
                                datetime.fromisoformat(row["fetched_at"]), row["id"])
                for row in rows]

    def get_prices_since(self, product_id: int, since: datetime) -> list[PriceRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM price_history WHERE product_id=? AND fetched_at>=? "
                "ORDER BY fetched_at DESC",
                (product_id, since.isoformat()),
            ).fetchall()
        return [self._price_from_row(row) for row in rows]

    def get_external_mapping(self, product_id: int, provider: str) -> ExternalProductMapping | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM product_external_mappings WHERE product_id=? AND provider=?",
                (product_id, provider),
            ).fetchone()
        if not row:
            return None
        return ExternalProductMapping(row["product_id"], row["provider"], row["external_id"],
                                      row["external_url"], row["match_method"],
                                      datetime.fromisoformat(row["matched_at"]))

    def save_external_mapping(self, mapping: ExternalProductMapping) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO product_external_mappings VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(product_id, provider) DO UPDATE SET external_id=excluded.external_id, "
                "external_url=excluded.external_url, match_method=excluded.match_method, "
                "matched_at=excluded.matched_at",
                (mapping.product_id, mapping.provider, mapping.external_id, mapping.external_url,
                 mapping.match_method, mapping.matched_at.isoformat()),
            )

    def delete_external_mapping(self, product_id: int, provider: str) -> None:
        with self._connect() as connection:
            mapping = connection.execute(
                "SELECT external_id FROM product_external_mappings WHERE product_id=? AND provider=?",
                (product_id, provider),
            ).fetchone()
            connection.execute(
                "DELETE FROM product_external_mappings WHERE product_id=? AND provider=?",
                (product_id, provider),
            )
            connection.execute(
                "DELETE FROM external_provider_status WHERE product_id=? AND provider=?",
                (product_id, provider),
            )
            if mapping:
                references = connection.execute(
                    "SELECT COUNT(*) AS count FROM product_external_mappings "
                    "WHERE provider=? AND external_id=?", (provider, mapping["external_id"]),
                ).fetchone()["count"]
                if references == 0:
                    connection.execute(
                        "DELETE FROM external_price_history WHERE provider=? AND external_product_id=?",
                        (provider, mapping["external_id"]),
                    )

    def save_external_provider_status(self, product_id: int, provider: str, status: str,
                                      message: str, item_count: int, checked_at: datetime) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO external_provider_status VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(product_id, provider) DO UPDATE SET status=excluded.status, "
                "message=excluded.message, item_count=excluded.item_count, checked_at=excluded.checked_at",
                (product_id, provider, status, message, item_count, checked_at.isoformat()),
            )

    def get_external_provider_status(self, product_id: int, provider: str) -> dict[str, object] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM external_provider_status WHERE product_id=? AND provider=?",
                (product_id, provider),
            ).fetchone()
        return dict(row) if row else None

    def purge_external_prices_before(self, before: datetime) -> int:
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM external_price_history WHERE observed_at < ?", (before.isoformat(),)
            )
            deleted = cursor.rowcount
            cursor.close()
        return deleted

    def save_external_prices(self, points: list[ExternalPricePoint]) -> None:
        if not points:
            return
        with self._connect() as connection:
            connection.executemany(
                "INSERT INTO external_price_history VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(provider, external_product_id, observed_at, price_type) "
                "DO UPDATE SET price=excluded.price, fetched_at=excluded.fetched_at",
                [(point.provider, point.external_product_id, point.price,
                  point.observed_at.isoformat(), point.price_type.value,
                  (point.fetched_at or datetime.now()).isoformat()) for point in points],
            )

    def get_external_prices(self, provider: str, external_id: str,
                            since: datetime) -> list[ExternalPricePoint]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM external_price_history WHERE provider=? AND external_product_id=? "
                "AND observed_at>=? ORDER BY observed_at DESC",
                (provider, external_id, since.isoformat()),
            ).fetchall()
        return [ExternalPricePoint(
            row["provider"], row["external_product_id"], row["price"],
            datetime.fromisoformat(row["observed_at"]), PriceHistoryType(row["price_type"]),
            datetime.fromisoformat(row["fetched_at"]),
        ) for row in rows]

    def get_price_history(self, product_id: int, limit: int = 500) -> list[PriceRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM price_history WHERE product_id=? "
                "ORDER BY fetched_at DESC LIMIT ?", (product_id, limit)
            ).fetchall()
        return [self._price_from_row(row) for row in rows]

    def get_daily_price_summaries(self, product_id: int, limit: int = 30) -> list[DailyPriceSummary]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT date(fetched_at) AS day, MIN(price) AS minimum_price, "
                "AVG(price) AS average_price, COUNT(*) AS sample_count "
                "FROM price_history WHERE product_id=? GROUP BY date(fetched_at) "
                "ORDER BY day DESC LIMIT ?", (product_id, limit)
            ).fetchall()
        return [DailyPriceSummary(
            day=datetime.strptime(row["day"], "%Y-%m-%d").date(),
            minimum_price=row["minimum_price"],
            average_price=row["average_price"],
            sample_count=row["sample_count"],
        ) for row in rows]

    @staticmethod
    def _product_from_row(row: sqlite3.Row) -> Product:
        return Product(id=row["id"], name=row["name"], category=row["category"],
                       url=row["url"], site=row["site"], enabled=bool(row["enabled"]),
                       stock_status=row["stock_status"],
                       specifications=tuple(tuple(item) for item in json.loads(
                           row["specifications_json"] or "[]"
                       )),
                       manufacturer=row["manufacturer"], model_number=row["model_number"],
                       jan_code=row["jan_code"],
                       created_at=datetime.fromisoformat(row["created_at"]))

    @staticmethod
    def _price_from_row(row: sqlite3.Row) -> PriceRecord:
        return PriceRecord(id=row["id"], product_id=row["product_id"], price=row["price"],
                           fetched_at=datetime.fromisoformat(row["fetched_at"]))
