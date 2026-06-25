#!/usr/bin/env python3
"""Conversation guardrail tests for Fede /care."""

from __future__ import annotations

import tempfile
import unittest
import json
from pathlib import Path
from unittest.mock import patch

import vida_selfcare
from vida_common import is_leaked_tool_call, strip_leaked_tool_calls


class VidaSelfcareTest(unittest.TestCase):
    def run_with_temp_data(self, text: str) -> dict:
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(vida_selfcare, "care_data", return_value=Path(tmp)):
                return vida_selfcare.handle(text) or {}

    def test_tinnitus_does_not_diagnose(self) -> None:
        payload = self.run_with_temp_data("Es un pitido en mi oído izquierdo que tengo hace más de 6 meses")
        reply = payload["whatsapp_reply"].lower()

        self.assertIn("tinnitus unilateral", reply)
        self.assertIn("no invento causas", reply)
        self.assertIn("mandíbula", reply)

    def test_supplements_are_not_treatment(self) -> None:
        payload = self.run_with_temp_data("Tomé melena de león, B12 complex y creatina")
        reply = payload["whatsapp_reply"].lower()

        self.assertIn("suplementos", reply)
        self.assertIn("no tratamiento", reply)
        self.assertIn("no asumo efecto clínico", reply)

    def test_crisis_gets_safety_response(self) -> None:
        payload = self.run_with_temp_data("No puedo más con esto")
        reply = payload["whatsapp_reply"].lower()

        self.assertIn("estás a salvo", reply)
        self.assertIn("emergencias", reply)

    def test_repetitive_feedback_acknowledges_and_pivots(self) -> None:
        payload = self.run_with_temp_data("siempre me das el mismo consejo")
        reply = payload["whatsapp_reply"].lower()
        self.assertIn("fede:", reply)
        self.assertIn("repetido", reply)
        self.assertIn("ánimo 0-10", reply)

    def test_health_data_query_reads_structured_log(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = root / "data"
            ctx = root / "context"
            data.mkdir()
            ctx.mkdir()
            (data / "selfcare_log.jsonl").write_text(
                json.dumps(
                    {
                        "at": "2026-06-17T10:49:43-04:00",
                        "intent": "sleep",
                        "text_preview": "dormí 5h, 3000 pasos",
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            (data / "selfcare_profile.json").write_text(
                json.dumps(vida_selfcare.DEFAULT_PROFILE, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            with patch.object(vida_selfcare, "care_data", return_value=data):

                def ctx_dir() -> Path:
                    return ctx

                with patch.object(vida_selfcare, "care_context_dir", ctx_dir):
                    payload = vida_selfcare.handle_health_data_query(
                        "dime que datos de salud registraste"
                    ) or {}

        reply = payload.get("whatsapp_reply", "")
        self.assertIn("Fede:", reply)
        self.assertIn("sleep", reply)
        self.assertIn("dormí 5h", reply)
        self.assertIn("tinnitus", reply.lower())

    def test_leaked_tool_call_detection(self) -> None:
        self.assertTrue(is_leaked_tool_call('memory_search(query="consejo repetido")'))
        self.assertTrue(is_leaked_tool_call("memory_get(path=\"foo.md\")"))
        self.assertFalse(is_leaked_tool_call("Fede: hoy prueba 10 min de caminata."))
        self.assertEqual(strip_leaked_tool_calls('memory_search(query="x")'), "")


if __name__ == "__main__":
    unittest.main()
