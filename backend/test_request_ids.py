#!/usr/bin/env python3
"""Unit tests for backend request correlation helpers."""

import unittest
import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from server import _resolve_request_id


class RequestIdHelperTests(unittest.TestCase):
    def test_resolve_request_id_uses_header_when_present(self):
        headers = {"X-Request-ID": "abc-123"}
        self.assertEqual(_resolve_request_id(headers), "abc-123")

    def test_resolve_request_id_falls_back_to_generated_value(self):
        value = _resolve_request_id({})
        self.assertIsInstance(value, str)
        self.assertGreaterEqual(len(value), 16)


if __name__ == "__main__":
    unittest.main(verbosity=2)
