"""Formatea ultimo scan LinkedIn Intel para WhatsApp (prioridad Chile)."""

from __future__ import annotations

import argparse
import json
import re
from datetime import date
from pathlib import Path

from linkedin_intel_region import chile_score, is_job_noise, pick_top_chile, region_cfg

ROOT = Path("/home/node/openclaw-mauro")
if not ROOT.exists():
    ROOT = Path(__file__).resolve().parent.parent

INTEL_DATA = ROOT / "data/workspace/marketing/intel/data"
DEFAULT_CONFIG = ROOT / "config/linkedin_intel/config.json"


def load_config() -> dict:
    if DEFAULT_CONFIG.exists():
        return json.loads(DEFAULT_CONFIG.read_text(encoding="utf-8"))
    return {}


def latest_signals_path() -> Path | None:
    today = INTEL_DATA / f"linkedin_signals_{date.today().isoformat()}.json"
    if today.exists():
        return today
    files = sorted(INTEL_DATA.glob("linkedin_signals_*.json"), reverse=True)
    return files[0] if files else None


def signal_title(sig: dict) -> str:
    text = (sig.get("text") or "").replace("\n", " ")
    m = re.search(r"(?:Publicaci[oó]n en el feed|Feed post)\s+(.+?)\s+•", text, re.I)
    if m:
        return m.group(1).strip()[:140]
    for sep in (" • ", " — ", " | "):
        if sep in text:
            return text.split(sep)[0].strip()[:140]
    return text[:140].strip()


def signal_url(sig: dict) -> str:
    url = (sig.get("url") or "").strip()
    if url:
        return url
    text = sig.get("text") or ""
    m = re.search(r"https?://(?:www\.)?linkedin\.com/\S+", text)
    return m.group(0).rstrip(").,") if m else ""


def format_whatsapp(payload: dict, cfg: dict | None = None) -> str:
    cfg = cfg or load_config()
    region = region_cfg(cfg)
    signals = payload.get("signals") or []
    count = payload.get("signal_count", len(signals))
    report_date = payload.get("date", "hoy")
    top, chile_count = pick_top_chile(signals, cfg, limit=6)

    lines = [
        f"Contenido Intel LinkedIn ({report_date}) — foco {region.get('name', 'Chile')}/LATAM",
        "",
        f"{count} senales totales · {chile_count} con contexto Chile/LATAM",
        "",
    ]
    if not signals:
        lines.extend([
            "No se encontraron posts en el ultimo scan.",
            "Re-login LinkedIn o corre scan en PC y sincroniza.",
            "",
        ])
        return "\n".join(lines)

    if chile_count == 0:
        lines.append("Pocas senales Chile hoy; muestro las mas relevantes LATAM/DevOps (sin ofertas US):")
    else:
        lines.append("Senales top:")
    lines.append("")

    for i, s in enumerate(top, 1):
        title = signal_title(s)
        url = signal_url(s)
        kw = s.get("keyword")
        tag = f" [{kw}]" if kw else ""
        chile_tag = " 🇨🇱" if chile_score(s.get("text", ""), cfg) > 0 else ""
        lines.append(f"{i}. {title}{tag}{chile_tag}")
        if url:
            lines.append(f"   🔗 {url}")
        elif (s.get("text") or "")[:120]:
            lines.append(f"   {(s.get('text') or '')[:160].replace(chr(10), ' ')}")

    lines.extend([
        "",
        "Ideas de angulo Chile (Innovacion Radical):",
        "• Traduce la tendencia a contexto enterprise Chile (DORA, costos AWS, compliance).",
        "• Evita copiar hype US; usa casos reales y espanol Chile.",
        "",
        "Borradores: drafts/linkedin/ (publicacion manual).",
        "Refresh: scan cada 12h desde PC o /intel linkedin tendencias",
    ])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    cfg = load_config()
    path = latest_signals_path()
    if not path:
        result = {
            "status": "empty",
            "whatsapp_reply": (
                "Aun no hay scan LinkedIn. "
                "Corre sync-linkedin-intel-to-server.ps1 en PC o espera cron 12h."
            ),
        }
    else:
        payload = json.loads(path.read_text(encoding="utf-8"))
        result = {
            "status": "ok",
            "source": str(path.name),
            "region": region_cfg(cfg).get("name", "Chile"),
            "whatsapp_reply": format_whatsapp(payload, cfg),
            "signal_count": payload.get("signal_count", 0),
        }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(result["whatsapp_reply"])


if __name__ == "__main__":
    main()
