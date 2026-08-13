import socket
import unittest
import urllib.error

from victor.fetch_errors import (ConnectionFailure, ProductUnavailableFailure,
                                 TimeoutFailure, classify_fetch_error)


class FetchErrorTest(unittest.TestCase):
    def test_classifies_page_removal(self) -> None:
        error = urllib.error.HTTPError("url", 404, "not found", {}, None)
        try:
            self.assertIsInstance(classify_fetch_error(error, "商品"), ProductUnavailableFailure)
        finally:
            error.close()

    def test_classifies_timeout(self) -> None:
        self.assertIsInstance(classify_fetch_error(socket.timeout(), "商品"), TimeoutFailure)

    def test_classifies_connection_failure(self) -> None:
        error = urllib.error.URLError("dns")
        self.assertIsInstance(classify_fetch_error(error, "商品"), ConnectionFailure)


if __name__ == "__main__":
    unittest.main()
