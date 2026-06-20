#!/usr/bin/env python3
"""Tests for runtime_paths legacy resolution."""

from __future__ import annotations

import unittest

from runtime_paths import cv_library_dir, logs_dir, resolve_repo_path, secrets_dir


class RuntimePathsTests(unittest.TestCase):
    def test_canonical_dirs_under_runtime(self) -> None:
        self.assertTrue(str(cv_library_dir()).endswith("runtime/jobs/cv-library"))
        self.assertTrue(str(secrets_dir()).endswith("runtime/secrets"))
        self.assertTrue(str(logs_dir()).endswith("runtime/logs"))

    def test_legacy_cv_aliases(self) -> None:
        self.assertEqual(resolve_repo_path("content/CV"), cv_library_dir())
        self.assertEqual(resolve_repo_path("data/CV/foo.pdf"), cv_library_dir() / "foo.pdf")

    def test_legacy_secret_aliases(self) -> None:
        self.assertEqual(
            resolve_repo_path("secrets/linkedin_storage_state.json"),
            secrets_dir() / "linkedin_storage_state.json",
        )
        self.assertEqual(resolve_repo_path("data/secrets/.env"), secrets_dir() / ".env")

    def test_runtime_paths_passthrough(self) -> None:
        self.assertEqual(
            resolve_repo_path("runtime/secrets/gmail_token.json"),
            secrets_dir() / "gmail_token.json",
        )

    def test_logs_alias(self) -> None:
        self.assertEqual(resolve_repo_path("logs/model-sync.log"), logs_dir() / "model-sync.log")


if __name__ == "__main__":
    unittest.main()
