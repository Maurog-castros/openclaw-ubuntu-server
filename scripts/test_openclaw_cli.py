#!/usr/bin/env python3
"""Tests for openclaw CLI resolution."""

from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest import mock

import openclaw_cli


class OpenclawCliTests(unittest.TestCase):
    def setUp(self) -> None:
        openclaw_cli._gateway_container.cache_clear()

    def test_openclaw_bin_override(self) -> None:
        with mock.patch.dict(os.environ, {"OPENCLAW_BIN": "/custom/openclaw"}, clear=False):
            openclaw_cli._gateway_container.cache_clear()
            self.assertEqual(
                openclaw_cli.openclaw_argv("agent", "--json"),
                ["/custom/openclaw", "agent", "--json"],
            )

    def test_docker_gateway_when_running(self) -> None:
        env = {k: v for k, v in os.environ.items() if k != "OPENCLAW_BIN"}
        with mock.patch.dict(os.environ, env, clear=True):
            openclaw_cli._gateway_container.cache_clear()
            with mock.patch(
                "openclaw_cli.subprocess.run",
                return_value=mock.Mock(returncode=0, stdout="true"),
            ):
                openclaw_cli._gateway_container.cache_clear()
                argv = openclaw_cli.openclaw_argv("agent", "--local")
                self.assertEqual(
                    argv[:4],
                    ["docker", "exec", openclaw_cli.DEFAULT_GATEWAY_CONTAINER, "openclaw"],
                )

    def test_local_submodule_fallback(self) -> None:
        env = {k: v for k, v in os.environ.items() if k not in {"OPENCLAW_BIN", "OPENCLAW_GATEWAY_CONTAINER"}}
        local = openclaw_cli.ROOT / "openclaw" / "node_modules" / ".bin" / "openclaw"
        with mock.patch.dict(os.environ, env, clear=True):
            openclaw_cli._gateway_container.cache_clear()
            with mock.patch("openclaw_cli.subprocess.run", return_value=mock.Mock(returncode=1, stdout="")):
                with mock.patch("openclaw_cli.shutil.which", return_value=None):
                    if not local.is_file():
                        self.skipTest("openclaw submodule CLI not installed")
                    argv = openclaw_cli.openclaw_argv("--version")
                    self.assertEqual(argv[0], str(local))


if __name__ == "__main__":
    unittest.main()
