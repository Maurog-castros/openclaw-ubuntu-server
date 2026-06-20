#!/usr/bin/env python3
"""Resolve openclaw CLI for host scripts outside the gateway container."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

ROOT = Path("/home/node/openclaw-mauro")
if not ROOT.exists():
    ROOT = Path(__file__).resolve().parent.parent

DEFAULT_GATEWAY_CONTAINER = "openclaw-openclaw-gateway-1"


@lru_cache(maxsize=1)
def _gateway_container() -> str | None:
    name = os.environ.get("OPENCLAW_GATEWAY_CONTAINER", DEFAULT_GATEWAY_CONTAINER).strip()
    if not name:
        return None
    proc = subprocess.run(
        ["docker", "inspect", "-f", "{{.State.Running}}", name],
        text=True,
        capture_output=True,
        timeout=5,
        check=False,
    )
    if proc.returncode == 0 and proc.stdout.strip() == "true":
        return name
    return None


def openclaw_argv(*args: str) -> list[str]:
    """Return argv to invoke `openclaw` with the given arguments."""
    override = os.environ.get("OPENCLAW_BIN", "").strip()
    if override:
        return [override, *args]

    container = _gateway_container()
    if container:
        return ["docker", "exec", container, "openclaw", *args]

    found = shutil.which("openclaw")
    if found:
        return [found, *args]

    local = ROOT / "openclaw" / "node_modules" / ".bin" / "openclaw"
    if local.is_file():
        return [str(local), *args]

    raise FileNotFoundError(
        "openclaw CLI not found: set OPENCLAW_BIN, start gateway container "
        f"{DEFAULT_GATEWAY_CONTAINER}, or install openclaw submodule deps"
    )


def main() -> None:
    if len(sys.argv) < 3 or sys.argv[1] != "exec":
        raise SystemExit("usage: openclaw_cli.py exec <openclaw-args...>")
    cmd = openclaw_argv(*sys.argv[2:])
    os.execvp(cmd[0], cmd)


if __name__ == "__main__":
    main()
