#!/usr/bin/env python3
"""Conversation guardrail tests for Fede /care."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import vida_selfcare


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


if __name__ == "__main__":
    unittest.main()
