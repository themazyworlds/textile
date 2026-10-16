import asyncio
import sys
import unittest

from mcp import ClientSession, types
from mcp.client.stdio import StdioServerParameters, stdio_client

from textile.core.orchestration.loom import loom
from textile.core.orchestration.twill import create_twill_server
from textile.core.security.policy import get_tier_policy


class TestTierPolicy(unittest.TestCase):
    """Unit tests for TierPolicy security matrix and get_tier_policy()."""

    def test_observe_tier_policy(self):
        policy = get_tier_policy("observe")
        self.assertFalse(policy.requires_2fa)
        self.assertTrue(policy.requires_sandbox)
        self.assertFalse(policy.workspace_writable)
        self.assertEqual(policy.default_timeout, 10.0)

    def test_interact_tier_policy(self):
        policy = get_tier_policy("interact")
        self.assertFalse(policy.requires_2fa)
        self.assertTrue(policy.requires_sandbox)
        self.assertFalse(policy.workspace_writable)
        self.assertEqual(policy.default_timeout, 15.0)

    def test_mutate_tier_policy(self):
        policy = get_tier_policy("mutate")
        self.assertTrue(policy.requires_2fa)
        self.assertTrue(policy.requires_sandbox)
        self.assertTrue(policy.workspace_writable)
        self.assertEqual(policy.default_timeout, 60.0)

    def test_privileged_tier_policy(self):
        policy = get_tier_policy("privileged")
        self.assertTrue(policy.requires_2fa)
        self.assertFalse(policy.requires_sandbox)
        self.assertTrue(policy.workspace_writable)
        self.assertEqual(policy.default_timeout, 300.0)

    def test_system_exec_tier_policy(self):
        policy = get_tier_policy("system_exec")
        self.assertTrue(policy.requires_2fa)
        self.assertTrue(policy.requires_sandbox)
        self.assertFalse(policy.workspace_writable)
        self.assertEqual(policy.default_timeout, 120.0)

    def test_invalid_tier_fails_closed(self):
        with self.assertRaises(ValueError):
            get_tier_policy("invalid_untrusted_tier")


class TestTwillServer(unittest.TestCase):
    def setUp(self):
        loom.initialize()

    def test_twill_server_creation(self):
        app = create_twill_server()
        self.assertEqual(app.name, "textile")

    def test_twill_stdio_client_connection(self):
        async def _run_test():
            params = StdioServerParameters(command=sys.executable, args=["-m", "textile.core.orchestration.twill"])
            async with (
                stdio_client(params) as (read_stream, write_stream),
                ClientSession(read_stream, write_stream) as session,
            ):
                await session.initialize()
                tools_res = await session.list_tools()
                self.assertGreater(len(tools_res.tools), 0)

                res = await session.call_tool("textile_get_state", {})
                self.assertIsNotNone(res.content)
                self.assertGreater(len(res.content), 0)
                item = res.content[0]
                text_content = item.text if isinstance(item, types.TextContent) else getattr(item, "text", "")
                self.assertIn("slots", text_content)

        asyncio.run(_run_test())


if __name__ == "__main__":
    unittest.main()
