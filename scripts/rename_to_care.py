#!/usr/bin/env python3
import json
import re
import shutil
from datetime import datetime
from pathlib import Path

ROOT = Path("/home/mauro/openclaw-mauro")
OLD_WS = ROOT / "data/workspace/vida"
NEW_WS = ROOT / "data/workspace/care"
CONFIG = ROOT / "data/config/openclaw.json"
SCR = ROOT / "scripts"

if OLD_WS.exists() and not NEW_WS.exists():
    shutil.move(str(OLD_WS), str(NEW_WS))
    print("workspace moved vida -> care")

for rel in ["SOUL.md", "AGENTS.md", "TOOLS.md", "IDENTITY.md", "TOOLS.md"]:
    p = NEW_WS / rel
    if p.exists():
        t = p.read_text(encoding="utf-8")
        t = (
            t.replace("/vida", "/care")
            .replace("Agente Vida", "Agente Care")
            .replace("agente vida", "agente care")
            .replace("workspace/vida", "workspace/care")
            .replace("**Name:** Vida", "**Name:** Care")
            .replace("- **Name:** Vida", "- **Name:** Care")
        )
        p.write_text(t, encoding="utf-8")

cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
agents = cfg.get("agents", {}).get("list", [])
out = []
for a in agents:
    if a.get("id") == "vida":
        a = dict(a)
        a["id"] = "care"
        a["name"] = "care"
        a["workspace"] = "/home/node/.openclaw/workspace/care"
        a["agentDir"] = "/home/node/.openclaw/agents/care/agent"
        ident = dict(a.get("identity") or {})
        ident["name"] = "Care"
        a["identity"] = ident
    out.append(a)
cfg["agents"]["list"] = out

am = cfg.setdefault("plugins", {}).setdefault("entries", {}).setdefault("active-memory", {}).setdefault("config", {})
am["agents"] = ["care" if x == "vida" else x for x in am.get("agents", [])]
if "care" not in am["agents"]:
    am["agents"].append("care")

for ch_key in ("telegram", "whatsapp"):
    ch = cfg.get("channels", {}).get(ch_key, {})
    for peer_cfg in ch.get("direct", {}).values():
        if "systemPrompt" in peer_cfg:
            peer_cfg["systemPrompt"] = peer_cfg["systemPrompt"].replace("/vida", "/care").replace("agente diario personal", "agente care diario personal")

bak = CONFIG.with_suffix(f".json.bak-care-{datetime.now().strftime('%Y%m%d-%H%M%S')}")
shutil.copy2(CONFIG, bak)
CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

new_dir = ROOT / "data/config/agents/care/agent"
new_dir.mkdir(parents=True, exist_ok=True)
old_dir = ROOT / "data/config/agents/vida/agent"
if old_dir.exists():
    for f in old_dir.iterdir():
        dest = new_dir / f.name
        if not dest.exists():
            shutil.copy2(f, dest)

fd = SCR / "finanzas_delegate.py"
text = fd.read_text(encoding="utf-8")
text = text.replace('VIDA_RE = re.compile(r"^\\s*/vida\\b", re.I)', 'CARE_RE = re.compile(r"^\\s*/care\\b", re.I)')
text = text.replace("VIDA_RE.search(raw_text)", "CARE_RE.search(raw_text)")
text = text.replace('"agent", "vida"', '"agent", "care"')
text = text.replace('agent="vida"', 'agent="care"')
text = text.replace('payload.setdefault("agent", "vida")', 'payload.setdefault("agent", "care")')
fd.write_text(text, encoding="utf-8")

for name in ["vida_delegate.py", "vida_common.py", "vida_checkin.py"]:
    p = SCR / name
    if p.exists():
        p.write_text(p.read_text(encoding="utf-8").replace("/vida", "/care").replace("workspace/vida", "workspace/care").replace('"vida"', '"care"'), encoding="utf-8")

print("rename to /care OK")
