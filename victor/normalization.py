from __future__ import annotations

import re
import unicodedata


def normalize_product_name(name: str) -> str:
    """Return a stable comparison form without guessing product identity."""
    normalized = unicodedata.normalize("NFKC", name).strip().casefold()
    return re.sub(r"\s+", " ", normalized)


def matches_product_name(name: str, query: str) -> bool:
    return normalize_product_name(query) in normalize_product_name(name)

