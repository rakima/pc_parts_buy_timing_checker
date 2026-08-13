import unittest

from victor.gui import ACCENT_COLORS, IMAGE_FILES, STATUS_IMAGE_SIZE
from victor.models import TimingStatus


class GuiResourcesTest(unittest.TestCase):
    def test_every_status_has_image_and_accent(self) -> None:
        for status in TimingStatus:
            with self.subTest(status=status):
                self.assertIn(status, IMAGE_FILES)
                self.assertIn(status, ACCENT_COLORS)

    def test_waiting_uses_default_image(self) -> None:
        self.assertEqual("victor_00_waiting.png", IMAGE_FILES[TimingStatus.WAITING])

    def test_status_images_use_square_display_area(self) -> None:
        self.assertEqual(STATUS_IMAGE_SIZE[0], STATUS_IMAGE_SIZE[1])


if __name__ == "__main__":
    unittest.main()
