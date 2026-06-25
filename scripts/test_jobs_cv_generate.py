#!/usr/bin/env python3
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from jobs_cv_builder import parse_vacancy, generate_cv_files
from jobs_cv_generate import looks_like_vacancy_paste

FALABELLA_SNIPPET = """
Falabella SpA
Falabella SpA - Grupo Falabella

Data Analyst
🇨🇱 Las Condes, Metropolitana
Publicado hace 51 días
Full Time
Presencial y remoto
Permanente (Indefinido)

Descripción
Oferta
Recopilar, analizar y reportar datos de HR para generar insights que mejoren decisiones.

- Levantar requerimientos, extraer/limpiar/integrar datos de RR.HH.
- Construir KPIs y dashboards.
- Analizar tendencias y entregar insights accionables.

Requisitos
Candidato/a
· Deseable conocimiento y/o experiencia en SQL
· Deseable conocimiento y/o experiencia en Power BI
· Deseable conocimiento y/o experiencia Python.
· Desde 1 año de experiencia en estadística y análisis de datos
"""


class JobsCvGenerateTest(unittest.TestCase):
    def test_parse_falabella_vacancy(self):
        info = parse_vacancy(FALABELLA_SNIPPET)
        self.assertIn("Falabella", info.company)
        self.assertIn("Data Analyst", info.title)
        self.assertEqual(info.role_key, "data_analyst")
        self.assertIn("sql", [k.lower() for k in info.keywords])

    def test_looks_like_vacancy_paste(self):
        self.assertTrue(looks_like_vacancy_paste(FALABELLA_SNIPPET))

    def test_generates_docx_and_pdf(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            result = generate_cv_files(FALABELLA_SNIPPET, out)
            docx = Path(result["docx"])
            pdf = Path(result["pdf"]) if result.get("pdf") else None
            self.assertTrue(docx.exists())
            self.assertGreater(docx.stat().st_size, 5000)
            self.assertIn("Data Analyst", result["whatsapp_reply"])
            self.assertIn("Falabella", result["whatsapp_reply"])
            if pdf:
                self.assertTrue(pdf.exists())
                self.assertGreater(pdf.stat().st_size, 1000)

    def test_whatsapp_intro_mentions_focus(self):
        info = parse_vacancy(FALABELLA_SNIPPET)
        from jobs_cv_builder import whatsapp_intro

        intro = whatsapp_intro(info)
        self.assertIn("ATS", intro)
        self.assertIn("Falabella", intro)
        self.assertIn("DevOps", intro)


if __name__ == "__main__":
    unittest.main()
