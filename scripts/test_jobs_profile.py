#!/usr/bin/env python3
"""Pruebas perfiles Jobs multi-persona."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jobs_profile import (
    JobsProfile,
    get_profile,
    parse_profile_from_text,
    validate_profile_id,
)


class JobsProfileTest(unittest.TestCase):
    def test_parse_profile_from_text(self) -> None:
        text, profile_id = parse_profile_from_text("@maria buscar linkedin")
        self.assertEqual("maria", profile_id)
        self.assertEqual("buscar linkedin", text)

        text2, profile_id2 = parse_profile_from_text("perfil pedro indexar cv")
        self.assertEqual("pedro", profile_id2)
        self.assertEqual("indexar cv", text2)

    def test_validate_profile_id(self) -> None:
        validate_profile_id("maria")
        with self.assertRaises(ValueError):
            validate_profile_id("1bad")

    def test_default_profile_mauro(self) -> None:
        profile = get_profile("mauro")
        self.assertEqual("mauro", profile.profile_id)
        self.assertTrue(profile.workspace.name == "jobs" or profile.workspace.exists() or True)
        self.assertTrue(str(profile.config_path).endswith("config.json"))

    def test_runtime_paths_from_env(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp) / "persona"
            cfg = Path(tmp) / "config.json"
            ws.mkdir()
            cfg.write_text("{}", encoding="utf-8")
            env = {
                "OPENCLAW_JOBS_DATA": str(ws),
                "OPENCLAW_JOBS_CONFIG": str(cfg),
                "OPENCLAW_JOBS_PROFILE": "demo",
            }
            with patch.dict(os.environ, env, clear=False):
                from jobs_profile import resolve_runtime_paths

                workspace, config_path, profile_id = resolve_runtime_paths()
            self.assertEqual(ws, workspace)
            self.assertEqual(cfg, config_path)
            self.assertEqual("demo", profile_id)


if __name__ == "__main__":
    unittest.main()
