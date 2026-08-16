import os
from pathlib import Path
from unittest.mock import patch
import unittest

from victor.paths import resource_root, user_data_root


class ApplicationPathTest(unittest.TestCase):
    def test_source_mode_uses_repository_root(self) -> None:
        self.assertEqual(resource_root(), user_data_root())

    def test_frozen_mode_uses_local_app_data(self) -> None:
        with patch("victor.paths.sys.frozen", True, create=True), \
                patch.dict(os.environ, {"LOCALAPPDATA": r"C:\Users\test\AppData\Local"}):
            self.assertEqual(
                Path(r"C:\Users\test\AppData\Local") / "VictorPriceChecker",
                user_data_root(),
            )


if __name__ == "__main__":
    unittest.main()
