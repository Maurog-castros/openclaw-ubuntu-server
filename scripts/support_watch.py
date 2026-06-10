#!/usr/bin/env python3
"""Watch cada 5 min: scan -> auto-fix -> commit+push."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from support_common import live_health
from support_remediate import remediate_auto
from support_scan_logs import scan


def main() -> None:
    parser = argparse.ArgumentParser(description="Support watch loop (cron 5m)")
    parser.add_argument("--no-commit", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    scan_result = scan()
    fix_result = {"status": "skip", "fixed": 0}
    if (
        scan_result.get("open_findings", 0) > 0
        or scan_result.get("new_findings", 0) > 0
        or live_health().get("needs_remediation")
    ):
        fix_result = remediate_auto(do_commit=not args.no_commit)

    payload = {
        "status": "ok",
        "scan": scan_result,
        "remediation": fix_result,
        "summary": (
            f"watch: nuevos={scan_result.get('new_findings')} "
            f"abiertos={scan_result.get('open_findings')} "
            f"fixed={fix_result.get('fixed', 0)}"
        ),
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(payload["summary"])


if __name__ == "__main__":
    main()
