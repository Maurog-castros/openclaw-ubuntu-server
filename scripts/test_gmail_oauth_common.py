#!/usr/bin/env python3
"""Tests para gmail_oauth_common."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from gmail_oauth_common import (  # noqa: E402
    GMAIL_MODIFY,
    GMAIL_READONLY,
    check_gmail_oauth_health,
    sync_legacy_tokens_from_workspace,
    token_file,
)


class GmailOAuthCommonTests(unittest.TestCase):
    def test_check_health_structure(self) -> None:
        result = check_gmail_oauth_health()
        self.assertIn("status", result)
        self.assertIn("tokens", result)
        self.assertEqual(len(result["tokens"]), 3)

    def test_sync_skips_when_workspace_missing(self) -> None:
        with patch("gmail_oauth_common._workspace_source_data", return_value=None):
            self.assertFalse(sync_legacy_tokens_from_workspace())

    def test_sync_writes_legacy_scopes(self) -> None:
        workspace = token_file("google_workspace_token.json")
        if not workspace.exists():
            self.skipTest("workspace token missing")
        source = json.loads(workspace.read_text(encoding="utf-8"))
        with patch("gmail_oauth_common._workspace_source_data", return_value=source):
            changed = sync_legacy_tokens_from_workspace(force=True)
        self.assertTrue(changed)
        modify = json.loads(token_file("gmail_modify_token.json").read_text())
        readonly = json.loads(token_file("gmail_token.json").read_text())
        self.assertIn(GMAIL_MODIFY, modify["scopes"])
        self.assertEqual(readonly["scopes"], [GMAIL_READONLY])


if __name__ == "__main__":
    unittest.main()
