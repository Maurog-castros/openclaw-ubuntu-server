#!/usr/bin/env python3
"""Playwright compartido para portales de empleo — reexport Laborum."""

from __future__ import annotations

from typing import Any

from jobs_laborum_browser import (
    ensure_login as ensure_laborum_login,
    is_logged_in as is_laborum_logged_in,
    launch_laborum_browser as launch_portal_browser,
    load_laborum_credentials,
    new_context as new_portal_context,
    save_session_if_logged_in,
    storage_state_path as portal_storage_path,
)


def portal_credentials(portal: str):
    if portal == "laborum":
        return load_laborum_credentials()
    return None


def save_portal_state(page: Any, portal: str, cfg=None):
    if portal != "laborum":
        raise ValueError(f"Portal no soportado: {portal}")
    saved = save_session_if_logged_in(page, cfg)
    if not saved:
        raise RuntimeError(f"No se guardo sesion {portal}: login no completado.")
    return saved
