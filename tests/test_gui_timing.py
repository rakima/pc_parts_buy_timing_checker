import unittest

from victor.gui import wait_for_minimum_duration


class GuiTimingTest(unittest.TestCase):
    def test_waits_only_for_remaining_duration(self) -> None:
        waits: list[float] = []
        wait_for_minimum_duration(
            started_at=10.0,
            minimum_seconds=3.0,
            clock=lambda: 11.25,
            sleeper=waits.append,
        )
        self.assertEqual([1.75], waits)

    def test_does_not_wait_when_work_already_took_long_enough(self) -> None:
        waits: list[float] = []
        wait_for_minimum_duration(
            started_at=10.0,
            minimum_seconds=3.0,
            clock=lambda: 13.1,
            sleeper=waits.append,
        )
        self.assertEqual([], waits)


if __name__ == "__main__":
    unittest.main()
