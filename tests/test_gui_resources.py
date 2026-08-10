import unittest

from victor.gui import ACCENT_COLORS, IMAGE_FILES
from victor.models import TimingStatus


class GuiResourcesTest(unittest.TestCase):
    def test_every_status_has_image_and_accent(self) -> None:
        for status in TimingStatus:
            with self.subTest(status=status):
                self.assertIn(status, IMAGE_FILES)
                self.assertIn(status, ACCENT_COLORS)

    def test_waiting_uses_default_image(self) -> None:
        self.assertEqual("victor_00_waiting.png", IMAGE_FILES[TimingStatus.WAITING])


if __name__ == "__main__":
    unittest.main()
