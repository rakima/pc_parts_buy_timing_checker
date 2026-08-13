from __future__ import annotations

import re
import unicodedata

from victor.models import ProductCandidate, ProductIdentity, ProductMatch
from victor.normalization import normalize_product_name


IDENTIFIER_KEYS = {
    "jan", "janコード", "jan code", "型番", "製品型番", "メーカー型番", "part number",
}
MANUFACTURER_KEYS = {"メーカー", "ブランド", "manufacturer", "brand"}


def normalize_identifier(value: str | None) -> str | None:
    if not value:
        return None
    normalized = unicodedata.normalize("NFKC", value).upper()
    normalized = re.sub(r"[^A-Z0-9]", "", normalized)
    return normalized or None


def identify_candidate(candidate: ProductCandidate) -> ProductIdentity:
    specs = {key.strip().casefold(): value.strip() for key, value in candidate.specifications}
    jan = next((value for key, value in specs.items() if key in IDENTIFIER_KEYS and re.fullmatch(r"\d{8}|\d{13}", re.sub(r"\D", "", value))), None)
    model = candidate.model_name
    if not model:
        model = next((value for key, value in specs.items() if key in IDENTIFIER_KEYS and value != jan), None)
    manufacturer = candidate.manufacturer or next(
        (value for key, value in specs.items() if key in MANUFACTURER_KEYS), None
    )
    if not model:
        model = _model_from_name(candidate.name)
    return ProductIdentity(
        manufacturer=normalize_product_name(manufacturer) if manufacturer else None,
        model_number=normalize_identifier(model),
        jan_code=re.sub(r"\D", "", jan) if jan else None,
    )


def match_candidates(source: ProductCandidate,
                     candidates: list[ProductCandidate]) -> list[ProductMatch]:
    source_identity = identify_candidate(source)
    matches: list[ProductMatch] = []
    for candidate in candidates:
        if candidate.url == source.url:
            continue
        identity = identify_candidate(candidate)
        if source_identity.jan_code and source_identity.jan_code == identity.jan_code:
            matches.append(ProductMatch(candidate, "一致", "JANコード一致"))
        elif source_identity.model_number and source_identity.model_number == identity.model_number:
            matches.append(ProductMatch(candidate, "一致", "メーカー型番一致"))
        elif _name_tokens(source.name) == _name_tokens(candidate.name):
            matches.append(ProductMatch(candidate, "候補", "正規化商品名一致"))
    return sorted(matches, key=lambda item: (item.confidence != "一致", item.candidate.price))


def _model_from_name(name: str) -> str | None:
    tokens = re.findall(r"(?=[A-Z0-9-]*[A-Z])(?=[A-Z0-9-]*\d)[A-Z0-9][A-Z0-9-]{4,}", name.upper())
    ignored = {"GEFORCE", "RADEON", "GDDR6", "GDDR7", "PCIE4", "PCIE5"}
    tokens = [token for token in tokens if token not in ignored]
    return max(tokens, key=len) if tokens else None


def _name_tokens(name: str) -> tuple[str, ...]:
    ignored = {"gpu", "cpu", "ssd", "メモリ", "グラフィックボード"}
    return tuple(token for token in re.findall(r"[a-z0-9]+", normalize_product_name(name))
                 if token not in ignored)
