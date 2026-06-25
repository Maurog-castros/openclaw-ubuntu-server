#!/usr/bin/env python3
"""Pruebas de inicializacion Google Sheets Jobs."""
from __future__ import annotations

import unittest

from jobs_google_sheet_setup import (
    CATALOGS, HEADERS, HISTORY_HEADERS, catalog_rows,
    structure_requests, validation,
)


class JobsGoogleSheetSetupTest(unittest.TestCase):
    def test_schema(self) -> None:
        self.assertEqual(32, len(HEADERS))
        self.assertEqual(len(HEADERS), len(set(HEADERS)))
        self.assertIn("resultado_entrevista", HEADERS)
        self.assertIn("fecha_proxima_accion", HEADERS)
        self.assertEqual(11, len(HISTORY_HEADERS))

    def test_catalogs(self) -> None:
        self.assertIn("contacto_reclutador", CATALOGS["Estados"])
        self.assertIn("entrevista_tecnica", CATALOGS["Estados"])
        self.assertIn("muy_bien", CATALOGS["Resultados_entrevista"])
        self.assertEqual(len(CATALOGS), len(catalog_rows()[0]["values"]))

    def test_structure_reuses_default_sheet(self) -> None:
        metadata = {"sheets": [{"properties": {
            "sheetId": 0, "title": "Hoja 1",
            "gridProperties": {"rowCount": 1000, "columnCount": 26},
        }}]}
        requests = structure_requests(metadata)
        keys = [next(iter(item)) for item in requests]
        self.assertIn("updateSheetProperties", keys)
        self.assertEqual(3, keys.count("addSheet"))
        self.assertTrue(all(len(item) == 1 for item in requests))

    def test_validation_range(self) -> None:
        request = validation(1, 13, "A", 13)["setDataValidation"]
        value = request["rule"]["condition"]["values"][0]["userEnteredValue"]
        self.assertEqual("=Catalogos!$A$2:$A$13", value)
        self.assertTrue(request["rule"]["strict"])


if __name__ == "__main__":
    unittest.main()
