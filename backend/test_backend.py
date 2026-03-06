#!/usr/bin/env python3
"""Automated integration tests for backend API endpoints."""

import os
import socket
import subprocess
import sys
import time
import unittest
from pathlib import Path

import requests


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        return sock.getsockname()[1]


class BackendApiIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.project_root = Path(__file__).resolve().parents[1]
        cls.port = _find_free_port()
        cls.base_url = f"http://127.0.0.1:{cls.port}"

        env = os.environ.copy()
        env["BACKEND_PORT"] = str(cls.port)

        cls.server_process = subprocess.Popen(
            [sys.executable, "backend/server.py"],
            cwd=str(cls.project_root),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )

        cls._wait_for_server_ready()

    @classmethod
    def tearDownClass(cls):
        if cls.server_process and cls.server_process.poll() is None:
            cls.server_process.terminate()
            try:
                cls.server_process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                cls.server_process.kill()
                cls.server_process.wait(timeout=5)

    @classmethod
    def _wait_for_server_ready(cls):
        deadline = time.time() + 40
        last_error = None
        while time.time() < deadline:
            if cls.server_process.poll() is not None:
                output = ""
                if cls.server_process.stdout:
                    output = cls.server_process.stdout.read()
                raise RuntimeError(f"Backend server exited early. Output:\n{output}")
            try:
                resp = requests.get(f"{cls.base_url}/health", timeout=2)
                if resp.status_code == 200:
                    return
            except requests.RequestException as e:
                last_error = e
            time.sleep(0.5)
        raise RuntimeError(f"Backend server did not become ready in time: {last_error}")

    def _assert_standard_error(self, payload: dict):
        self.assertIn("success", payload)
        self.assertFalse(payload["success"])
        self.assertIn("error", payload)
        self.assertIsInstance(payload["error"], str)
        self.assertIn("error_code", payload)
        self.assertIsInstance(payload["error_code"], str)

    def test_liveness_endpoint(self):
        response = requests.get(f"{self.base_url}/health", timeout=5)
        self.assertEqual(response.status_code, 200)
        self.assertIn("X-Request-ID", response.headers)
        self.assertTrue(response.headers.get("X-Request-ID"))
        payload = response.json()
        self.assertEqual(payload.get("status"), "ok")
        self.assertEqual(payload.get("service"), "backend")
        self.assertEqual(payload.get("check"), "liveness")

    def test_not_found_uses_standard_error_schema(self):
        response = requests.get(f"{self.base_url}/unknown-route", timeout=5)
        self.assertEqual(response.status_code, 404)
        payload = response.json()
        self._assert_standard_error(payload)
        self.assertEqual(payload.get("error_code"), "not_found")

    def test_create_and_list_sessions(self):
        create_resp = requests.post(
            f"{self.base_url}/sessions",
            json={"title": "Test Session", "model": "gemma3:4b-cloud"},
            timeout=5,
        )
        self.assertEqual(create_resp.status_code, 201)
        create_data = create_resp.json()

        self.assertIn("session_id", create_data)
        self.assertIn("session", create_data)
        session_id = create_data["session_id"]

        list_resp = requests.get(f"{self.base_url}/sessions", timeout=5)
        self.assertEqual(list_resp.status_code, 200)
        list_data = list_resp.json()

        self.assertIn("sessions", list_data)
        self.assertIn("total", list_data)
        self.assertTrue(any(s.get("id") == session_id for s in list_data["sessions"]))

    def test_session_message_validation_error(self):
        create_resp = requests.post(
            f"{self.base_url}/sessions",
            json={"title": "Validation Session", "model": "gemma3:4b-cloud"},
            timeout=5,
        )
        self.assertEqual(create_resp.status_code, 201)
        session_id = create_resp.json()["session_id"]

        msg_resp = requests.post(
            f"{self.base_url}/sessions/{session_id}/messages",
            json={"message": ""},
            timeout=5,
        )
        self.assertEqual(msg_resp.status_code, 400)
        payload = msg_resp.json()
        self._assert_standard_error(payload)
        self.assertEqual(payload.get("error_code"), "bad_request")

    def test_rename_session_validation_error(self):
        create_resp = requests.post(
            f"{self.base_url}/sessions",
            json={"title": "Rename Session", "model": "gemma3:4b-cloud"},
            timeout=5,
        )
        self.assertEqual(create_resp.status_code, 201)
        session_id = create_resp.json()["session_id"]

        rename_resp = requests.post(
            f"{self.base_url}/sessions/{session_id}/rename",
            json={"title": "   "},
            timeout=5,
        )
        self.assertEqual(rename_resp.status_code, 400)
        payload = rename_resp.json()
        self._assert_standard_error(payload)
        self.assertEqual(payload.get("error_code"), "bad_request")


if __name__ == "__main__":
    unittest.main(verbosity=2)