"""Stress OpenClaw agent path with qwen3-coder-next."""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
OPENCLAW = ROOT / "openclaw"


def build_long_message(lines: int) -> str:
    body = "\n".join(
        f"{i:04d}: BL MAEU{i:07d}, ETA nullable, category food, amount {1000+i} CLP"
        for i in range(lines)
    )
    return (
        "Stress largo OpenClaw. Cuenta lineas y responde solo JSON con keys "
        "line_count, first_bl, last_amount.\n"
        f"{body}"
    )


def run_agent(name: str, agent: str, message: str, timeout: int = 300) -> dict[str, Any]:
    cmd = [
        "docker",
        "compose",
        "exec",
        "-T",
        "openclaw-gateway",
        "openclaw",
        "agent",
        "--agent",
        agent,
        "--model",
        "remote-lm/openclaw-remote",
        "--session-key",
        f"agent:{agent}:qwen-stress-{name}",
        "--message",
        message,
        "--json",
        "--timeout",
        str(timeout),
    ]
    started = time.perf_counter()
    proc = subprocess.run(
        cmd,
        cwd=str(OPENCLAW),
        text=True,
        capture_output=True,
        timeout=timeout + 30,
        check=False,
    )
    elapsed = round(time.perf_counter() - started, 2)
    result: dict[str, Any] = {
        "name": name,
        "agent": agent,
        "returncode": proc.returncode,
        "seconds": elapsed,
        "ok": False,
    }
    if proc.returncode != 0:
        result["stderr"] = proc.stderr[-1200:]
        result["stdout"] = proc.stdout[-1200:]
        return result
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        result["stdout"] = proc.stdout[-1200:]
        return result
    result_obj = payload.get("result") or {}
    meta = result_obj.get("meta") or {}
    agent_meta = meta.get("agentMeta") or {}
    budget = agent_meta.get("contextBudgetStatus") or {}
    result.update(
        {
            "ok": payload.get("status") == "ok",
            "status": payload.get("status"),
            "text": ((result_obj.get("payloads") or [{}])[0].get("text") or "")[:240],
            "provider": agent_meta.get("provider"),
            "model": agent_meta.get("model"),
            "contextTokens": agent_meta.get("contextTokens"),
            "estimatedPromptTokens": budget.get("estimatedPromptTokens"),
            "remainingPromptBudgetTokens": budget.get("remainingPromptBudgetTokens"),
            "fallbackUsed": (meta.get("executionTrace") or {}).get("fallbackUsed"),
        }
    )
    return result


def main() -> None:
    tests = [
        ("main_long_16k_chars", "main", build_long_message(220), 300),
        ("finanzas_toolfree", "finanzas", "Responde exactamente: finanzas-qwen-ok", 240),
    ]
    results = [run_agent(name, agent, msg, timeout) for name, agent, msg, timeout in tests]
    print(json.dumps({"ok": all(r.get("ok") for r in results), "results": results}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
