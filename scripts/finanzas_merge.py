"""Une Lider + vision + transferencias en un CSV maestro de movimientos."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from finanzas_common import (
    DEFAULT_CARTOLA_CSV,
    DEFAULT_LIDER_CSV,
    DEFAULT_TRANSFERENCIAS_CSV,
    DEFAULT_UNIFIED_CSV,
    DEFAULT_VISION_CSV,
    merge_all_sources,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Genera CSV unificado de finanzas.")
    parser.add_argument("--output", default=DEFAULT_UNIFIED_CSV)
    parser.add_argument("--lider", default=DEFAULT_LIDER_CSV)
    parser.add_argument("--vision", default=DEFAULT_VISION_CSV)
    parser.add_argument("--transferencias", default=DEFAULT_TRANSFERENCIAS_CSV)
    parser.add_argument("--cartola", default=DEFAULT_CARTOLA_CSV)
    parser.add_argument("--owner-rut", default="", help="RUT propio para clasificar entradas/salidas.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    stats = merge_all_sources(
        unified_csv=Path(args.output),
        lider_csv=Path(args.lider),
        vision_csv=Path(args.vision),
        transferencias_csv=Path(args.transferencias),
        owner_rut=args.owner_rut,
        cartola_csv=Path(args.cartola),
    )

    if args.json:
        print(json.dumps({"output": args.output, **stats}, ensure_ascii=False, indent=2))
    else:
        print(f"CSV unificado: {args.output}")
        print(f"Lider: {stats['lider']} filas")
        print(f"Vision: {stats['vision']} filas")
        print(f"Transferencias: {stats['transferencias']} filas")
        print(f"Cartola: {stats['cartola']} filas")
        print(f"Total unificado (deduplicado): {stats['unified']} filas")


if __name__ == "__main__":
    main()
