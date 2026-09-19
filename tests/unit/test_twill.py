import asyncio
import sys
import unittest
from textile.core.cli import _layer_info
from textile.core.base import (
    LAYER_BASE,
    LAYER_DESKTOP_PROTOCOL,
    LAYER_COMPOSITOR_DE,
    LAYER_SESSION_MANAGER,
    LAYER_USER_OVERRIDE,
)
from textile.core.loom import loom
from textile.core.twill import create_twill_server

try:
    from mcp.client.stdio import StdioServerParameters, stdio_client
    from mcp import ClientSession
    MCP_CLIENT_AVAILABLE = True
except ImportError:
    MCP_CLIENT_AVAILABLE = False


class TestLayerHierarchy(unittest.TestCase):
    """Unit tests for _layer_info() in textile.core.cli."""

    def test_core_posix_layer(self):
        t = _layer_info(LAYER_BASE)
        self.assertEqual(t["name"], "Core POSIX")
        self.assertEqual(t["level"], 1)

    def test_below_base_falls_back_to_core_posix(self):
        t = _layer_info(1)
        self.assertEqual(t["level"], 1)

    def test_desktop_protocol_layer(self):
        t = _layer_info(LAYER_DESKTOP_PROTOCOL)
        self.assertEqual(t["name"], "Desktop Protocol")
        self.assertEqual(t["level"], 2)

    def test_compositor_de_layer(self):
        t = _layer_info(LAYER_COMPOSITOR_DE)
        self.assertEqual(t["name"], "Compositor / DE")
        self.assertEqual(t["level"], 3)

    def test_session_manager_layer(self):
        t = _layer_info(LAYER_SESSION_MANAGER)
        self.assertEqual(t["name"], "Session Manager")
        self.assertEqual(t["level"], 4)

    def test_user_override_layer(self):
        t = _layer_info(LAYER_USER_OVERRIDE)
        self.assertEqual(t["name"], "User Override")
        self.assertEqual(t["level"], 5)

    def test_above_user_override(self):
        t = _layer_info(9999)
        self.assertEqual(t["level"], 5)

    def test_layer_ordering(self):
        """Higher numeric layer must always produce a higher or equal level."""
        layers = [
            LAYER_BASE,
            LAYER_DESKTOP_PROTOCOL,
            LAYER_COMPOSITOR_DE,
            LAYER_SESSION_MANAGER,
            LAYER_USER_OVERRIDE,
        ]
        levels = [_layer_info(p)["level"] for p in layers]
        self.assertEqual(levels, sorted(levels))


class TestTwillServer(unittest.TestCase):
    def setUp(self):
        loom.initialize()

    def test_twill_server_creation(self):
        app = create_twill_server()
        self.assertEqual(app.name, "textile")

    def test_twill_stdio_client_connection(self):
        if not MCP_CLIENT_AVAILABLE:
            self.skipTest("mcp client SDK not available")

        async def _run_test():
            params = StdioServerParameters(command=sys.executable, args=["-m", "textile.core.twill"])
            async with stdio_client(params) as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    tools_res = await session.list_tools()
                    self.assertGreater(len(tools_res.tools), 0)

                    res = await session.call_tool("textile_get_state", {})
                    self.assertIsNotNone(res.content)
                    self.assertGreater(len(res.content), 0)
                    self.assertIn("slots", res.content[0].text)

        asyncio.run(_run_test())


if __name__ == "__main__":
    unittest.main()
