#!/usr/bin/env python3
"""Regression tests for WhatsApp user isolation."""

from __future__ import annotations

import unittest

from channel_user_context import peer_from_session_key, resolve_user_context


class ChannelUserContextTest(unittest.TestCase):
    def test_known_owner_phone_resolves_owner(self) -> None:
        ctx = resolve_user_context(peer="+56945046845")

        self.assertEqual(ctx.user_id, "mauro")
        self.assertIs(ctx.is_owner, True)
        self.assertEqual(ctx.data_root.name, "data")

    def test_known_guest_phone_resolves_separate_data_root(self) -> None:
        ctx = resolve_user_context(peer="+56977605211")

        self.assertEqual(ctx.user_id, "user7760")
        self.assertIs(ctx.is_owner, False)
        self.assertIn("data/users/user7760", str(ctx.data_root).replace("\\", "/"))
        self.assertNotIn("supp", ctx.allowed_agents)

    def test_missing_phone_never_falls_back_to_owner(self) -> None:
        ctx = resolve_user_context(session_key="main:whatsapp:direct")

        self.assertTrue(ctx.user_id.startswith("guest_"))
        self.assertIs(ctx.is_owner, False)
        self.assertNotEqual(ctx.data_root.name, "data")
        self.assertEqual(ctx.allowed_agents, frozenset({"fin", "care"}))

    def test_session_key_extracts_whatsapp_peer_variants(self) -> None:
        self.assertEqual(peer_from_session_key("main:whatsapp:direct:+56977605211"), "+56977605211")
        self.assertEqual(peer_from_session_key("main:whatsapp:+56977605211"), "+56977605211")
        self.assertEqual(
            peer_from_session_key("main:whatsapp:default:dm:+56977605211:thread"),
            "+56977605211",
        )


if __name__ == "__main__":
    unittest.main()
