#!/usr/bin/env python3
"""Unit tests for resumable index build metadata helpers."""

import unittest
import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from server import _get_pending_file_paths


class ResumeIndexingMetadataTests(unittest.TestCase):
    def test_pending_files_excludes_completed(self):
        all_files = [
            "C:/docs/a.pdf",
            "C:/docs/b.pdf",
            "C:/docs/c.pdf",
        ]
        completed = ["C:/docs/a.pdf", "C:/docs/c.pdf"]

        pending = _get_pending_file_paths(all_files, completed)

        self.assertEqual(pending, ["C:/docs/b.pdf"])

    def test_pending_files_all_completed(self):
        all_files = ["C:/docs/a.pdf"]
        completed = ["C:/docs/a.pdf"]

        pending = _get_pending_file_paths(all_files, completed)

        self.assertEqual(pending, [])

    def test_pending_files_when_no_checkpoints(self):
        all_files = ["C:/docs/a.pdf", "C:/docs/b.pdf"]

        pending = _get_pending_file_paths(all_files, None)

        self.assertEqual(pending, all_files)


if __name__ == "__main__":
    unittest.main(verbosity=2)
