#!/usr/bin/env python3
from __future__ import annotations

import unittest

from jobs_computrabajo_browser import (
    HOME_URL,
    LOGIN_URL,
    is_logged_in,
    load_computrabajo_credentials,
    storage_state_path,
)


class ComputrabajoBrowserTest(unittest.TestCase):
    def test_urls(self):
        self.assertIn("acceso", LOGIN_URL)
        self.assertIn("candidate/home", HOME_URL)

    def test_load_credentials_from_env(self):
        creds = load_computrabajo_credentials()
        self.assertIsNotNone(creds, "Se esperan credenciales en runtime/secrets/.env")
        email, password = creds
        self.assertIn("@", email)
        self.assertGreater(len(password), 3)
        self.assertTrue(str(storage_state_path()).endswith("computrabajo_storage_state.json"))

    def test_is_logged_in_on_home(self):
        class FakePage:
            url = HOME_URL

            def inner_text(self, _sel):
                return "Mis postulaciones Alertas de empleo"

        self.assertTrue(is_logged_in(FakePage()))

    def test_is_logged_in_on_acceso(self):
        class FakePage:
            url = LOGIN_URL

            def inner_text(self, _sel):
                return "Ingresa y postulate"

        self.assertFalse(is_logged_in(FakePage()))


if __name__ == "__main__":
    unittest.main()
