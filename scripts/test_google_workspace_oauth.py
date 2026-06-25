#!/usr/bin/env python3
"""Pruebas enfocadas para OAuth Google Workspace."""

from __future__ import annotations

import json
import stat
import tempfile
import unittest
from pathlib import Path

from google_workspace_oauth import (
    SCOPES,
    callback_parameters,
    load_client_config,
    pkce_pair,
    write_secret_json,
)


class GoogleWorkspaceOAuthTest(unittest.TestCase):
    def test_pkce_pair_is_url_safe(self) -> None:
        verifier, challenge = pkce_pair()
        self.assertGreaterEqual(len(verifier), 43)
        self.assertNotIn("=", challenge)
        self.assertTrue(challenge)

    def test_callback_parameters(self) -> None:
        result = callback_parameters(
            "http://localhost:44567/?state=state-1&code=code-1"
        )
        self.assertEqual({"code": "code-1", "state": "state-1"}, result)

    def test_callback_rejection_is_explicit(self) -> None:
        with self.assertRaises(PermissionError):
            callback_parameters(
                "http://localhost:44567/?error=access_denied&state=state-1"
            )

    def test_client_config_accepts_installed_credentials(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "credentials.json"
            path.write_text(
                json.dumps(
                    {
                        "installed": {
                            "client_id": "client",
                            "client_secret": "secret",
                        }
                    }
                ),
                encoding="utf-8",
            )
            self.assertEqual("client", load_client_config(path)["client_id"])

    def test_secret_write_is_atomic_and_private(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "token.json"
            write_secret_json(path, {"token": "not-a-real-token"})
            self.assertEqual(
                {"token": "not-a-real-token"},
                json.loads(path.read_text(encoding="utf-8")),
            )
            self.assertEqual(0, stat.S_IMODE(path.stat().st_mode) & 0o077)

    def test_required_services_have_scopes(self) -> None:
        joined = " ".join(SCOPES)
        for service in ("gmail", "calendar", "spreadsheets", "drive.file"):
            self.assertIn(service, joined)


if __name__ == "__main__":
    unittest.main()
