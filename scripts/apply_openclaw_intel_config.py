#!/usr/bin/env python3
"""Aplica reglas Intel al agente (Daily Radar ES + YouTube) en SOUL + AGENTS."""

from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path("/home/mauro/openclaw-mauro")
INTEL_SOUL = REPO_ROOT / "data/workspace/marketing/intel/SOUL.md"
INTEL_AGENTS = REPO_ROOT / "data/workspace/marketing/intel/AGENTS.md"
RADAR_ES = REPO_ROOT / "config/marketing/intel-daily-radar-es.md"
YOUTUBE_SKILL = REPO_ROOT / "config/marketing/intel-youtube-skill.md"
MARKER_RADAR = "<!-- DAILY_RADAR_ES -->"
MARKER_YOUTUBE = "<!-- INTEL_YOUTUBE -->"


def backup(path: Path) -> None:
    if path.exists():
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        shutil.copy2(path, path.with_suffix(path.suffix + f".bak-intel-{stamp}"))


def upsert_marker_section(target: Path, source: Path, marker: str) -> bool:
    if not source.exists():
        return False
    block = source.read_text(encoding="utf-8").strip() + "\n"
    current = target.read_text(encoding="utf-8") if target.exists() else ""
    if marker in current:
        before, _, after = current.partition(marker)
        tail_idx = after.find("\n<!--")
        tail = after[tail_idx + 1 :] if tail_idx >= 0 else ""
        new_text = before.rstrip() + "\n\n" + block + (("\n" + tail.lstrip()) if tail else "")
    else:
        new_text = (current.rstrip() + "\n\n" + block) if current.strip() else block
    if new_text == current:
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(new_text, encoding="utf-8")
    return True


def main() -> int:
    backup(INTEL_SOUL)
    backup(INTEL_AGENTS)
    soul_radar = upsert_marker_section(INTEL_SOUL, RADAR_ES, MARKER_RADAR)
    agents_radar = upsert_marker_section(INTEL_AGENTS, RADAR_ES, MARKER_RADAR)
    soul_yt = upsert_marker_section(INTEL_SOUL, YOUTUBE_SKILL, MARKER_YOUTUBE)
    agents_yt = upsert_marker_section(INTEL_AGENTS, YOUTUBE_SKILL, MARKER_YOUTUBE)
    print(
        json.dumps(
            {
                "ok": True,
                "soul": str(INTEL_SOUL),
                "agents": str(INTEL_AGENTS),
                "soul_changed": soul_radar or soul_yt,
                "agents_changed": agents_radar or agents_yt,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
