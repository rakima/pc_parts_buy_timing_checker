import unittest

from victor.identity import identify_candidate, match_candidates, normalize_identifier
from victor.models import ProductCandidate


class ProductIdentityTest(unittest.TestCase):
    def candidate(self, name: str, shop: str = "ツクモ", price: int = 100,
                  specs: tuple[tuple[str, str], ...] = ()) -> ProductCandidate:
        return ProductCandidate(name, price, f"https://example.com/{shop}/{price}", shop, "GPU",
                                specifications=specs)

    def test_normalizes_model_number(self) -> None:
        self.assertEqual("GVN507TGAMINGOC12GD", normalize_identifier("GV-N507T-GAMING OC-12GD"))

    def test_extracts_jan_and_model_from_specs(self) -> None:
        identity = identify_candidate(self.candidate(
            "GPU", specs=(("JANコード", "4988755 067890"), ("メーカー型番", "ABC-123"))))
        self.assertEqual("4988755067890", identity.jan_code)
        self.assertEqual("ABC123", identity.model_number)

    def test_prefers_strong_model_match_and_sorts_by_price(self) -> None:
        source = self.candidate("ASUS RTX 5070 ABC-123", specs=(("型番", "ABC-123"),))
        candidates = [
            self.candidate("ASUS RTX 5070", "ドスパラ", 120, (("製品型番", "ABC123"),)),
            self.candidate("ASUS RTX 5070", "ドスパラ", 90, (("製品型番", "ABC-123"),)),
        ]
        matches = match_candidates(source, candidates)
        self.assertEqual([90, 120], [match.candidate.price for match in matches])
        self.assertTrue(all(match.confidence == "一致" for match in matches))


if __name__ == "__main__":
    unittest.main()
