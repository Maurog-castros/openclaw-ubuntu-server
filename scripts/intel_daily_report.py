"""Build Intel Daily Intelligence Report from HN, Reddit, GitHub and LinkedIn."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from datetime import date
from pathlib import Path
from typing import Any

from intel_localize import Localizer
from linkedin_intel_region import pick_top_chile

ROOT = Path("/home/node/openclaw-mauro") if Path("/home/node/openclaw-mauro").exists() else Path(__file__).resolve().parent.parent
INTEL_CONFIG = ROOT / "config/linkedin_intel/config.json"
INTEL_WS = ROOT / "data/workspace/marketing/intel"
RAW = INTEL_WS / "trends_raw.md"
REPORTS = INTEL_WS / "reports"
INTEL_DATA = INTEL_WS / "data"
RELEVANT = [
    "agent", "agents", "ai", "llm", "codex", "github", "devops", "sre", "kubernetes",
    "observability", "opentelemetry", "security", "token", "ci", "cd", "gpu", "cloud",
    "cost", "finops", "rag", "infrastructure", "ebpf", "gateway", "logs", "metrics",
    "trace", "tracing", "platform", "automation", "production", "error", "incident",
    "mlops", "machine learning",
]
NOISE = ["pokemon", "polo", "horse", "image archive", "bucky", "radio", "aesthetic"]
PAIN_HINTS = [
    "token", "security", "error", "incident", "cost", "gpu", "cloud", "rag", "ai",
    "kubernetes", "production", "mlops", "llm", "observability", "devops", "agent",
]


def refresh_sources() -> None:
    subprocess.run(["node", "fetch_trends.js"], cwd=str(INTEL_WS), timeout=90, check=False, capture_output=True, text=True)


def section(text: str, start: str, end_prefixes: list[str]) -> str:
    idx = text.find(start)
    if idx == -1:
        return ""
    tail = text[idx + len(start):]
    stops = [tail.find(prefix) for prefix in end_prefixes if tail.find(prefix) != -1]
    return tail[: min(stops)] if stops else tail


def bullets(block: str) -> list[str]:
    return [ln.strip()[2:].strip() for ln in block.splitlines() if ln.strip().startswith("- ")]


def score(line: str) -> int:
    low = line.lower()
    return sum(2 for t in RELEVANT if t in low) - sum(3 for t in NOISE if t in low)


def top_relevant(items: list[str], limit: int) -> list[str]:
    ranked = sorted(((score(x), x) for x in items), key=lambda x: x[0], reverse=True)
    return [x for s, x in ranked if s > 0][:limit] or items[:limit]


def parse_repo(line: str) -> dict[str, Any] | None:
    m = re.match(r"([^—]+) — ⭐?([0-9.]+) — (.*)", line)
    if not m:
        return None
    return {"name": m.group(1).strip(), "stars": m.group(2).strip(), "desc": m.group(3).strip()}


def github_topics(text: str) -> list[dict[str, Any]]:
    block = section(text, "## GitHub Topics", [])
    repos: list[dict[str, Any]] = []
    for line in bullets(block):
        repo = parse_repo(line)
        if repo and repo["name"] not in {r["name"] for r in repos}:
            repos.append(repo)
    priority_names = ["netdata", "langfuse", "signoz", "kong", "kestra", "airflow", "qdrant", "kubernetes"]
    repos.sort(
        key=lambda r: (any(p in r["name"].lower() for p in priority_names), score(r["name"] + " " + r["desc"])),
        reverse=True,
    )
    return repos[:8]


def clean_title(item: str) -> str:
    return re.sub(r"\s+", " ", item).strip()


def linkedin_title(text: str) -> str:
    m = re.search(r"(?:Publicaci[oó]n en el feed|Feed post)\s+(.+?)\s+•", text, re.I)
    if m:
        return m.group(1).strip()[:120]
    for sep in (" • ", " — ", " | "):
        if sep in text:
            return text.split(sep)[0].strip()[:120]
    return text[:120].strip()


def load_intel_config() -> dict[str, Any]:
    if INTEL_CONFIG.exists():
        return json.loads(INTEL_CONFIG.read_text(encoding="utf-8"))
    return {}


def load_linkedin_signals() -> list[dict[str, Any]]:
    today = INTEL_DATA / f"linkedin_signals_{date.today().isoformat()}.json"
    path = today if today.exists() else None
    if path is None:
        files = sorted(INTEL_DATA.glob("linkedin_signals_*.json"), reverse=True)
        path = files[0] if files else None
    if not path:
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    signals = list(payload.get("signals") or [])
    cfg = load_intel_config()
    top, _ = pick_top_chile(signals, cfg, limit=12)
    return top


def derive_content_ideas(pains: list[str], repos: list[dict[str, Any]], linkedin: list[dict]) -> list[str]:
    ideas = [
        "10 dolores reales en CI/CD con agentes IA (casos Chile)",
        "Observabilidad LLM en produccion: OpenTelemetry + Langfuse/SigNoz",
        "FinOps AWS/GCP en Chile: GPU, inferencia y costos fuera de control",
        "RAG corporativo LATAM: PDFs, imagenes y tablas en empresas reguladas",
    ]
    blob = " ".join(pains).lower()
    if "mlops" in blob or any("mlops" in (s.get("keyword") or "") for s in linkedin):
        ideas.insert(0, "MLOps en produccion: del notebook al pipeline con agentes")
    if "token" in blob or "llm" in blob:
        ideas.insert(0, "Tokenomics y costos LLM: lo que FinOps debe medir ya")
    if "security" in blob or "shadow" in blob:
        ideas.insert(0, "Shadow AI en enterprise: politicas sin matar innovacion")
    return list(dict.fromkeys(ideas))[:5]


def derive_product_ideas(pains: list[str], repos: list[dict[str, Any]]) -> list[str]:
    ideas = [
        "Plantilla de seguridad DevOps para agentes IA",
        "Auditoria FinOps cloud para cargas LLM",
        "Kit de observabilidad LLM con OpenTelemetry + dashboards",
        "Ebook/curso RAG Corporativo operacional",
    ]
    names = " ".join(r["name"].lower() for r in repos)
    if "langfuse" in names or "signoz" in names:
        ideas.insert(0, "Assessment observabilidad LLM (Langfuse/SigNoz) para empresas Chile")
    return list(dict.fromkeys(ideas))[:5]


def prospect_priority(name: str, desc: str) -> str:
    low = (name + " " + desc).lower()
    if "observability" in low or "opentelemetry" in low or "langfuse" in low or "signoz" in low:
        return "Alta (observabilidad/LLM ops)"
    if "workflow" in low or "airflow" in low or "mlops" in low or "ml" in low:
        return "Media-Alta (MLOps/automatizacion)"
    if "kubernetes" in low or "devops" in low:
        return "Alta (DevOps enterprise)"
    return "Media (senal tecnica)"


def build_report(raw: str, linkedin_signals: list[dict[str, Any]] | None = None) -> str:
    linkedin_signals = linkedin_signals if linkedin_signals is not None else load_linkedin_signals()
    hn_items = top_relevant(bullets(section(raw, "# Hacker News Top 20", ["## Reddit"])), 6)
    reddit_items = top_relevant(bullets(section(raw, "## Reddit", ["## GitHub Trending", "## GitHub Topics"])), 8)
    repos = github_topics(raw)

    loc = Localizer()
    for repo in repos[:6]:
        loc.queue(repo["desc"], max_len=loc.max_desc)
    for item in hn_items[:6] + reddit_items[:8]:
        loc.queue_title(item)
    for sig in linkedin_signals[:8]:
        loc.queue(linkedin_title(sig.get("text", "")))
    loc.flush()

    trend_lines: list[str] = []
    for repo in repos[:4]:
        name = repo["name"]
        desc_es = loc.desc(repo["desc"])
        trend_lines.append(f"• *{name} ({repo['stars']} estrellas)*: {desc_es}")
    for item in hn_items[:3]:
        title = loc.title(item)
        metric = ""
        sm = re.search(r"score:([0-9]+)", item)
        cm = re.search(r"comments:([0-9]+)", item)
        if sm:
            metric = f" — {sm.group(1)} pts HN"
            if cm:
                metric += f", {cm.group(1)} comentarios"
        trend_lines.append(f"• *{title}*{metric}")
    for sig in linkedin_signals[:4]:
        kw = sig.get("keyword") or "linkedin"
        title = loc.text(linkedin_title(sig.get("text", "")))
        trend_lines.append(f"• *LinkedIn [{kw}]*: {title}")

    pain_candidates = list(hn_items) + list(reddit_items)
    pains: list[str] = []
    for item in pain_candidates:
        low = item.lower()
        if any(t in low for t in PAIN_HINTS):
            pains.append(loc.title(item))
    for sig in linkedin_signals[:8]:
        text = sig.get("text", "")
        low = text.lower()
        if any(t in low for t in PAIN_HINTS):
            pains.append(loc.text(linkedin_title(text)))
    pains = list(dict.fromkeys(p for p in pains if p))[:7]

    prospects = []
    for repo in repos[:6]:
        name = repo["name"].split("/")[-1]
        prospects.append((name, repo["stars"], prospect_priority(repo["name"], repo["desc"])))

    content_ideas = derive_content_ideas(pains, repos, linkedin_signals)
    product_ideas = derive_product_ideas(pains, repos)

    lines = [
        f"🧭 *Intel Daily Consolidado — {date.today().isoformat()}*",
        "",
        "───",
        "",
        "🔥 Tendencias Fuertes",
        "",
        *(trend_lines[:9] or ["• Sin senales fuertes; revisar fuentes manualmente."]),
        "",
        "🎯 Dolores Reales (Oportunidades)",
        "",
    ]
    for i, pain in enumerate(pains[:5], 1):
        lines.append(f"{i}. *{pain}*")
    if not pains:
        lines.append("1. *No hubo dolores claros hoy* — mantener monitoreo")
    lines += ["", "📊 Prospectos Detectados", "", "| Empresa | Stars | Prioridad |", "| --- | --- | --- |"]
    for name, stars, pr in prospects[:5]:
        lines.append(f"| {name} | {stars} | {pr} |")
    lines += ["", "💡 Ideas de Contenido", ""]
    lines += [f"• {x}" for x in content_ideas]
    lines += ["", "💰 Ideas de Producto", ""]
    lines += [f"• {x}" for x in product_ideas]
    lines += [
        "",
        "📡 Fuentes usadas",
        "",
        "• Hacker News — historias destacadas",
        "• Reddit r/devops, r/sre, r/MachineLearning",
        "• GitHub topics: devops, mlops, observabilidad, kubernetes",
        f"• LinkedIn Innovacion Radical — foco Chile ({len(linkedin_signals)} senales)",
        "",
        "───",
        "",
        "¿Quieres que profundice en alguna tendencia o genere contenido para una oportunidad especifica?",
    ]
    return "\n".join(lines)


def format_whatsapp(report: str) -> str:
    """Convierte tablas markdown a texto plano para WhatsApp."""
    out: list[str] = []
    in_table = False
    for line in report.splitlines():
        if line.strip().startswith("|") and "---" in line:
            in_table = True
            continue
        if in_table and line.strip().startswith("|"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) >= 3 and cells[0].lower() not in ("empresa", "company"):
                out.append(f"• {cells[0]} ({cells[1]} ⭐) — {cells[2]}")
            continue
        if in_table and not line.strip().startswith("|"):
            in_table = False
        out.append(line)
    return "\n".join(out)


def main() -> None:
    parser = argparse.ArgumentParser(description="Intel daily full report")
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if args.refresh or not RAW.exists():
        refresh_sources()
    raw = RAW.read_text(encoding="utf-8", errors="ignore") if RAW.exists() else ""
    linkedin = load_linkedin_signals()
    report = build_report(raw, linkedin)
    REPORTS.mkdir(parents=True, exist_ok=True)
    out = REPORTS / f"{date.today().isoformat()}-consolidated.md"
    out.write_text(report + "\n", encoding="utf-8")
    payload = {
        "status": "ok",
        "report_file": str(out),
        "linkedin_signals": len(linkedin),
        "whatsapp_reply": format_whatsapp(report),
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(payload["whatsapp_reply"])


if __name__ == "__main__":
    main()
