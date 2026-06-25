#!/usr/bin/env python3
"""Inicializa Google Sheets para seguimiento de postulaciones Jobs."""
from __future__ import annotations

import argparse
import json
import urllib.parse
from typing import Any

import requests
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

from google_workspace_oauth import SCOPES, TOKEN_PATH, write_secret_json

HEADERS = [
    "job_id", "portal", "empresa", "cargo", "url_vacante", "ubicacion",
    "modalidad", "fecha_publicacion", "fecha_descubrimiento", "score_vacante",
    "cv_base", "score_cv_base", "cv_adaptado", "estado", "fecha_postulacion",
    "me_contactaron", "canal_contacto", "fecha_contacto", "reclutador",
    "entrevista_agendada", "fecha_entrevista", "tipo_entrevista",
    "resultado_entrevista", "siguiente_etapa", "proxima_accion",
    "fecha_proxima_accion", "dias_sin_movimiento", "prioridad",
    "renta_ofrecida", "motivo_cierre", "notas", "ultima_actualizacion",
]
HISTORY_HEADERS = [
    "evento_id", "job_id", "fecha_evento", "estado_anterior", "estado_nuevo",
    "canal", "contacto", "detalle", "proxima_accion",
    "fecha_proxima_accion", "registrado_por",
]
CATALOGS = {
    "Estados": [
        "descubierta", "analizada", "pendiente_aprobacion", "aprobada",
        "postulada", "contacto_reclutador", "entrevista_rrhh",
        "entrevista_tecnica", "oferta", "rechazada", "retirada", "cerrada",
    ],
    "Portales": ["linkedin", "chiletrabajos", "laborum", "otro"],
    "Modalidades": ["remoto", "hibrido", "presencial", "sin_dato"],
    "Si_No": ["no", "si"],
    "Canales": ["telefono", "email", "linkedin", "whatsapp", "videollamada", "otro"],
    "Tipos_entrevista": ["rrhh", "tecnica", "jefatura", "cliente", "prueba_tecnica", "otra"],
    "Resultados_entrevista": [
        "pendiente", "muy_bien", "bien", "regular", "mal",
        "avanza", "no_avanza", "sin_respuesta",
    ],
    "Prioridades": ["alta", "media", "baja", "descartada"],
    "Motivos_cierre": [
        "oferta_aceptada", "rechazo_empresa", "rechazo_candidato",
        "sin_respuesta", "vacante_cerrada", "renta", "modalidad", "otro",
    ],
    "Siguiente_etapa": [
        "sin_definir", "contactar_reclutador", "entrevista_rrhh",
        "entrevista_tecnica", "entrevista_jefatura", "prueba_tecnica",
        "referencias", "oferta", "cerrar",
    ],
}
SPECS = {
    "Postulaciones": (1000, len(HEADERS)),
    "Historial": (1000, len(HISTORY_HEADERS)),
    "Dashboard": (100, 10),
    "Catalogos": (100, len(CATALOGS)),
}
API = "https://sheets.googleapis.com/v4/spreadsheets"
# Google Sheets es_CL usa ";" como separador de argumentos en formulas.
FS = ";"


def get_credentials() -> Credentials:
    if not TOKEN_PATH.exists():
        raise FileNotFoundError(f"No existe token: {TOKEN_PATH}")
    creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        write_secret_json(TOKEN_PATH, json.loads(creds.to_json()))
    if not creds.valid or not creds.has_scopes(SCOPES):
        raise PermissionError("Token Google Workspace invalido o incompleto.")
    return creds


class Client:
    def __init__(self) -> None:
        self.creds = get_credentials()

    def request(self, method: str, url: str, **kwargs: Any) -> dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self.creds.token}",
            "Content-Type": "application/json",
        }
        response = requests.request(method, url, headers=headers, timeout=60, **kwargs)
        if response.status_code >= 400:
            try:
                message = (response.json().get("error") or {}).get("message", "")
            except ValueError:
                message = ""
            raise RuntimeError(f"Sheets HTTP {response.status_code}: {message[:500]}")
        return response.json()

    def metadata(self, spreadsheet_id: str) -> dict[str, Any]:
        fields = urllib.parse.quote(
            "properties,sheets(properties,basicFilter,conditionalFormats,charts(chartId))",
            safe=",()",
        )
        return self.request("GET", f"{API}/{spreadsheet_id}?fields={fields}")

    def batch(self, spreadsheet_id: str, requests_: list[dict[str, Any]]) -> None:
        self.request(
            "POST",
            f"{API}/{spreadsheet_id}:batchUpdate",
            json={"requests": requests_},
        )


def text_cell(value: str) -> dict[str, Any]:
    return {"userEnteredValue": {"stringValue": value}}


def formula_cell(value: str) -> dict[str, Any]:
    return {"userEnteredValue": {"formulaValue": value}}


def cells(values: list[str]) -> dict[str, Any]:
    return {"values": [text_cell(value) for value in values]}


def rng(sid: int, r0: int, r1: int, c0: int, c1: int) -> dict[str, int]:
    return {
        "sheetId": sid, "startRowIndex": r0, "endRowIndex": r1,
        "startColumnIndex": c0, "endColumnIndex": c1,
    }


def sheets(metadata: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {item["properties"]["title"]: item for item in metadata.get("sheets", [])}


def structure_requests(metadata: dict[str, Any]) -> list[dict[str, Any]]:
    existing = sheets(metadata)
    requests_: list[dict[str, Any]] = [{
        "updateSpreadsheetProperties": {
            "properties": {"timeZone": "America/Santiago"},
            "fields": "timeZone",
        }
    }]
    if "Postulaciones" not in existing:
        default = existing.get("Hoja 1")
        if default:
            requests_.append({"updateSheetProperties": {
                "properties": {
                    "sheetId": default["properties"]["sheetId"],
                    "title": "Postulaciones",
                },
                "fields": "title",
            }})
        else:
            requests_.append({"addSheet": {"properties": {"title": "Postulaciones"}}})
    for title in ("Historial", "Dashboard", "Catalogos"):
        if title not in existing:
            rows, cols = SPECS[title]
            requests_.append({"addSheet": {"properties": {
                "title": title,
                "gridProperties": {
                    "rowCount": rows, "columnCount": cols, "frozenRowCount": 1,
                },
            }}})
    return requests_


def catalog_rows() -> list[dict[str, Any]]:
    names = list(CATALOGS)
    result = [cells(names)]
    for index in range(max(map(len, CATALOGS.values()))):
        result.append(cells([
            CATALOGS[name][index] if index < len(CATALOGS[name]) else ""
            for name in names
        ]))
    return result


def dashboard_rows() -> list[dict[str, Any]]:
    result = [
        {"values": [text_cell("Indicador"), text_cell("Valor")]},
        {"values": [text_cell("Total oportunidades"), formula_cell("=COUNTA(Postulaciones!A2:A1000)")]},
        {"values": [text_cell("Pendientes aprobacion"), formula_cell(f'=COUNTIF(Postulaciones!N2:N1000{FS}"pendiente_aprobacion")')]},
        {"values": [text_cell("Postuladas"), formula_cell(f'=COUNTIF(Postulaciones!N2:N1000{FS}"postulada")')]},
        {"values": [text_cell("Me contactaron"), formula_cell(f'=COUNTIF(Postulaciones!P2:P1000{FS}"si")')]},
        {"values": [text_cell("Entrevistas agendadas"), formula_cell(f'=COUNTIF(Postulaciones!T2:T1000{FS}"si")')]},
        {"values": [text_cell("Ofertas"), formula_cell(f'=COUNTIF(Postulaciones!N2:N1000{FS}"oferta")')]},
        {"values": [text_cell("Seguimientos vencidos"), formula_cell(
            f'=COUNTIFS(Postulaciones!Z2:Z1000{FS}"<"&TODAY(){FS}Postulaciones!Z2:Z1000{FS}"<>"'
            f'{FS}Postulaciones!N2:N1000{FS}"<>rechazada"{FS}Postulaciones!N2:N1000{FS}"<>retirada"'
            f'{FS}Postulaciones!N2:N1000{FS}"<>cerrada")',
        )]},
        {"values": []},
        {"values": [text_cell("Estado"), text_cell("Cantidad")]},
    ]
    for status in CATALOGS["Estados"]:
        result.append({"values": [
            text_cell(status),
            formula_cell(f'=COUNTIF(Postulaciones!N2:N1000{FS}"{status}")'),
        ]})
    return result


def header_format(sid: int, cols: int) -> dict[str, Any]:
    return {"repeatCell": {
        "range": rng(sid, 0, 1, 0, cols),
        "cell": {"userEnteredFormat": {
            "backgroundColor": {"red": 0.9, "green": 0.9, "blue": 0.9},
            "textFormat": {"bold": True},
            "horizontalAlignment": "CENTER",
            "verticalAlignment": "MIDDLE",
            "wrapStrategy": "WRAP",
        }},
        "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment,verticalAlignment,wrapStrategy)",
    }}


def validation(sid: int, column: int, catalog_col: str, end_row: int) -> dict[str, Any]:
    reference = "=Catalogos!$" + catalog_col + "$2:$" + catalog_col + "$" + str(end_row)
    return {"setDataValidation": {
        "range": rng(sid, 1, 1000, column, column + 1),
        "rule": {
            "condition": {
                "type": "ONE_OF_RANGE",
                "values": [{"userEnteredValue": reference}],
            },
            "strict": True,
            "showCustomUi": True,
        },
    }}


def width(sid: int, start: int, end: int, pixels: int) -> dict[str, Any]:
    return {"updateDimensionProperties": {
        "range": {
            "sheetId": sid, "dimension": "COLUMNS",
            "startIndex": start, "endIndex": end,
        },
        "properties": {"pixelSize": pixels},
        "fields": "pixelSize",
    }}


def core_requests(metadata: dict[str, Any]) -> list[dict[str, Any]]:
    items = sheets(metadata)
    ids = {name: item["properties"]["sheetId"] for name, item in items.items()}
    p, h, d, c = ids["Postulaciones"], ids["Historial"], ids["Dashboard"], ids["Catalogos"]
    req: list[dict[str, Any]] = []
    for title, (rows, cols) in SPECS.items():
        props = items[title]["properties"]["gridProperties"]
        req.append({"updateSheetProperties": {
            "properties": {
                "sheetId": ids[title],
                "gridProperties": {
                    "rowCount": max(rows, props.get("rowCount", rows)),
                    "columnCount": max(cols, props.get("columnCount", cols)),
                    "frozenRowCount": 1,
                },
            },
            "fields": "gridProperties.rowCount,gridProperties.columnCount,gridProperties.frozenRowCount",
        }})
    req += [
        {"updateCells": {
            "range": rng(p, 0, 1, 0, len(HEADERS)),
            "rows": [cells(HEADERS)], "fields": "userEnteredValue",
        }},
        {"updateCells": {
            "range": rng(h, 0, 1, 0, len(HISTORY_HEADERS)),
            "rows": [cells(HISTORY_HEADERS)], "fields": "userEnteredValue",
        }},
        {"updateCells": {
            "start": {"sheetId": c, "rowIndex": 0, "columnIndex": 0},
            "rows": catalog_rows(), "fields": "userEnteredValue",
        }},
        {"updateCells": {
            "start": {"sheetId": d, "rowIndex": 0, "columnIndex": 0},
            "rows": dashboard_rows(), "fields": "userEnteredValue",
        }},
        header_format(p, len(HEADERS)), header_format(h, len(HISTORY_HEADERS)),
        header_format(c, len(CATALOGS)), header_format(d, 2),
    ]
    specs = [
        (1, "B", "Portales"), (6, "C", "Modalidades"), (13, "A", "Estados"),
        (15, "D", "Si_No"), (16, "E", "Canales"), (19, "D", "Si_No"),
        (21, "F", "Tipos_entrevista"), (22, "G", "Resultados_entrevista"),
        (23, "J", "Siguiente_etapa"), (27, "H", "Prioridades"),
        (29, "I", "Motivos_cierre"),
    ]
    req += [
        validation(p, col, letter, len(CATALOGS[name]) + 1)
        for col, letter, name in specs
    ]
    req += [
        validation(h, 3, "A", len(CATALOGS["Estados"]) + 1),
        validation(h, 4, "A", len(CATALOGS["Estados"]) + 1),
        validation(h, 5, "E", len(CATALOGS["Canales"]) + 1),
    ]
    req.append({"repeatCell": {
        "range": rng(p, 1, 1000, 26, 27),
        "cell": {
            "userEnteredValue": {"formulaValue": f'=IF(A2=""{FS}""{FS}TODAY()-MAX(I2{FS}O2{FS}R2))'},
            "userEnteredFormat": {"numberFormat": {"type": "NUMBER", "pattern": "0"}},
        },
        "fields": "userEnteredValue,userEnteredFormat.numberFormat",
    }})
    for start, end in ((7, 9), (14, 15), (17, 18), (20, 21), (25, 26), (31, 32)):
        req.append({"repeatCell": {
            "range": rng(p, 1, 1000, start, end),
            "cell": {"userEnteredFormat": {
                "numberFormat": {"type": "DATE", "pattern": "yyyy-mm-dd"}
            }},
            "fields": "userEnteredFormat.numberFormat",
        }})
    req.append({"repeatCell": {
        "range": rng(p, 1, 1000, 28, 29),
        "cell": {"userEnteredFormat": {
            "numberFormat": {"type": "CURRENCY", "pattern": "$#,##0"}
        }},
        "fields": "userEnteredFormat.numberFormat",
    }})
    if items["Postulaciones"].get("basicFilter"):
        req.append({"clearBasicFilter": {"sheetId": p}})
    req.append({"setBasicFilter": {"filter": {
        "range": rng(p, 0, 1000, 0, len(HEADERS))
    }}})
    for index in reversed(range(len(items["Postulaciones"].get("conditionalFormats", [])))):
        req.append({"deleteConditionalFormatRule": {"sheetId": p, "index": index}})
    rules = [
        ('=AND($Z2<>"";$Z2<TODAY())', {"red": 1.0, "green": 0.85, "blue": 0.85}),
        ('=$N2="oferta"', {"red": 0.82, "green": 0.94, "blue": 0.82}),
        ('=$N2="rechazada"', {"red": 0.9, "green": 0.9, "blue": 0.9}),
        ('=$N2="retirada"', {"red": 0.9, "green": 0.9, "blue": 0.9}),
        ('=$N2="cerrada"', {"red": 0.9, "green": 0.9, "blue": 0.9}),
    ]
    for formula, color in rules:
        req.append({"addConditionalFormatRule": {
            "index": 0,
            "rule": {
                "ranges": [rng(p, 1, 1000, 0, len(HEADERS))],
                "booleanRule": {
                    "condition": {
                        "type": "CUSTOM_FORMULA",
                        "values": [{"userEnteredValue": formula}],
                    },
                    "format": {"backgroundColor": color},
                },
            },
        }})
    for start, end, pixels in [
        (0, 2, 110), (2, 4, 190), (4, 5, 280), (5, 7, 150),
        (7, 10, 120), (10, 14, 170), (14, 26, 150), (26, 28, 120),
        (28, 32, 180),
    ]:
        req.append(width(p, start, end, pixels))
    req.append({"updateCells": {
        "range": rng(d, 99, 100, 7, 9),
        "rows": [{"values": [{}, {}]}],
        "fields": "userEnteredValue",
    }})
    req += [
        width(h, 0, len(HISTORY_HEADERS), 160),
        width(d, 0, 1, 220), width(d, 1, 2, 120),
        width(c, 0, len(CATALOGS), 170),
    ]
    return req


def chart_requests(metadata: dict[str, Any]) -> list[dict[str, Any]]:
    dashboard = sheets(metadata)["Dashboard"]
    d = dashboard["properties"]["sheetId"]
    req = [
        {"deleteEmbeddedObject": {"objectId": chart["chartId"]}}
        for chart in dashboard.get("charts", [])
        if chart.get("chartId")
    ]
    end = 10 + len(CATALOGS["Estados"])
    req.append({"addChart": {"chart": {
        "spec": {
            "title": "Oportunidades por estado",
            "basicChart": {
                "chartType": "COLUMN", "legendPosition": "NO_LEGEND",
                "domains": [{"domain": {"sourceRange": {
                    "sources": [rng(d, 10, end, 0, 1)]
                }}}],
                "series": [{"series": {"sourceRange": {
                    "sources": [rng(d, 10, end, 1, 2)]
                }}}],
                "headerCount": 0,
            },
        },
        "position": {"overlayPosition": {
            "anchorCell": {"sheetId": d, "rowIndex": 1, "columnIndex": 3},
            "widthPixels": 680, "heightPixels": 360,
        }},
    }}})
    return req


def setup(spreadsheet_id: str) -> dict[str, Any]:
    client = Client()
    metadata = client.metadata(spreadsheet_id)
    client.batch(spreadsheet_id, structure_requests(metadata))
    metadata = client.metadata(spreadsheet_id)
    client.batch(spreadsheet_id, core_requests(metadata))
    metadata = client.metadata(spreadsheet_id)
    client.batch(spreadsheet_id, chart_requests(metadata))
    final = client.metadata(spreadsheet_id)
    return {
        "status": "ok",
        "spreadsheet_id": spreadsheet_id,
        "url": f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit",
        "sheets": sorted(sheets(final)),
        "postulaciones_columns": len(HEADERS),
        "dropdowns": 14,
        "chart": bool(sheets(final)["Dashboard"].get("charts")),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spreadsheet-id", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm", default="")
    args = parser.parse_args()
    if not args.apply or args.confirm != "UPDATE-JOBS-SHEET":
        raise PermissionError("Requiere --apply --confirm UPDATE-JOBS-SHEET")
    print(json.dumps(setup(args.spreadsheet_id), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
