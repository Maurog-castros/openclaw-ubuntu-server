#!/usr/bin/env python3
"""Regression tests for /care routing."""

from __future__ import annotations

import unittest
from unittest.mock import patch

import vida_delegate


class VidaDelegateRoutingTest(unittest.TestCase):
    def test_add_to_diary_beats_medication_keywords(self) -> None:
        calls: list[tuple[str, tuple[str, ...]]] = []

        def fake_run_script(script: str, *args: str, timeout: int = 200) -> dict:
            calls.append((script, args))
            return {"status": "ok", "whatsapp_reply": "ok"}

        text = (
            "/care agrega esto a mi diario : me tome un diclofenaco y 1/4 "
            "de la pastilla para dormir.... aun sigo con el sonido en mi oifo"
        )

        with patch.object(vida_delegate, "run_script", side_effect=fake_run_script):
            payload = vida_delegate.route(text)

        self.assertEqual(payload["status"], "ok")
        self.assertEqual(calls[0][0], "vida_diary.py")
        self.assertEqual(calls[0][1][0], "--text")
        self.assertEqual(
            calls[0][1][1],
            "me tome un diclofenaco y 1/4 de la pastilla para dormir.... aun sigo con el sonido en mi oifo",
        )


if __name__ == "__main__":
    unittest.main()
