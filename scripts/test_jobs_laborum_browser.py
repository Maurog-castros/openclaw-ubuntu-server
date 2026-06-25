#!/usr/bin/env python3
from __future__ import annotations

import unittest

from jobs_laborum_browser import load_laborum_credentials, save_session, storage_state_path


class LaborumBrowserTest(unittest.TestCase):
    def test_load_credentials_from_env(self):
        creds = load_laborum_credentials()
        self.assertIsNotNone(creds, "Se esperan credenciales laborum en runtime/secrets/.env")
        email, password = creds
        self.assertIn("@", email)
        self.assertGreater(len(password), 3)

    def test_storage_state_path(self):
        self.assertTrue(str(storage_state_path()).endswith("laborum_storage_state.json"))

    def test_extract_mfa_from_subject(self):
        from jobs_laborum_mfa_gmail import extract_mfa_code

        self.assertEqual(extract_mfa_code("Tu código de acceso es: 004744"), "004744")
        self.assertEqual(extract_mfa_code("Tu codigo de acceso es: 154960", ""), "154960")

    def test_save_session_requires_login(self):
        class FakePage:
            url = "https://www.laborum.cl/candidatos/ingresar"

            def content(self):
                return "Ingresa a tu cuenta"

            def inner_text(self, _sel):
                return "Ingresa a tu cuenta olvidaste la clave"

            def get_by_role(self, *_a, **_k):
                class Loc:
                    def count(self):
                        return 1

                    def first(self):
                        return self

                    def is_visible(self):
                        return True

                return Loc()

        with self.assertRaises(RuntimeError):
            save_session(FakePage())


if __name__ == "__main__":
    unittest.main()
