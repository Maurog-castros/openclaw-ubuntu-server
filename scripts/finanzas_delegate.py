"""Compat: usar channel_delegate.py (router canal). Mantiene imports legacy."""

from __future__ import annotations

from channel_delegate import *  # noqa: F403

if __name__ == "__main__":
    from channel_delegate import main

    main()
