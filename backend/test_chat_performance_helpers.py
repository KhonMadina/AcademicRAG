#!/usr/bin/env python3
"""Unit tests for backend chat performance helpers."""

import unittest
import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from server import _is_plain_conversational_message, _prepare_conversation_history


class ChatPerformanceHelperTests(unittest.TestCase):
    def test_prepare_conversation_history_removes_duplicate_latest_user_message(self):
        history = [
            {"role": "user", "content": "First question"},
            {"role": "assistant", "content": "First answer"},
            {"role": "user", "content": "Second question"},
        ]

        prepared = _prepare_conversation_history(history, latest_user_message="Second question", max_messages=10)

        self.assertEqual(
            prepared,
            [
                {"role": "user", "content": "First question"},
                {"role": "assistant", "content": "First answer"},
            ],
        )

    def test_prepare_conversation_history_trims_to_recent_messages(self):
        history = [{"role": "user" if i % 2 == 0 else "assistant", "content": f"m{i}"} for i in range(8)]

        prepared = _prepare_conversation_history(history, latest_user_message="latest", max_messages=4)

        self.assertEqual(prepared, history[-4:])

    def test_plain_conversational_message_detects_greeting(self):
        self.assertTrue(_is_plain_conversational_message("Hi there"))
        self.assertTrue(_is_plain_conversational_message("Thanks"))

    def test_plain_conversational_message_ignores_document_query(self):
        self.assertFalse(_is_plain_conversational_message("Summarize the uploaded PDF document"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
