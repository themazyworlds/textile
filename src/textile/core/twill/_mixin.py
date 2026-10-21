"""
Textile Twill Coordinator Mixin.
Unifies LLM instruction generation, MCP tool schemas, and MCP stdio server execution.
"""

from typing import Any

lazy from textile.core.loom.mesh import loom
lazy from textile.core.skein.mesh import skein
lazy from textile.core.twill.instructions import fabric_instructions
lazy from textile.core.twill.mesh import run_twill


class TwillMixin:
    """Mixin providing agent context and MCP server methods for Camshaft."""

    @staticmethod
    def build_system_instructions() -> str:
        """Build unified system instructions for LLM/MCP context directly."""
        return fabric_instructions.build_instructions(skein.get_active_yarns())

    @staticmethod
    def get_mcp_tool_definitions() -> list[dict[str, Any]]:
        """Retrieve MCP JSON-RPC tool schemas for all active strands directly."""
        return fabric_instructions.get_mcp_definitions(loom.get_all_strands())

    @staticmethod
    def run_twill_server() -> None:
        """Start the official Twill Model Context Protocol (MCP) stdio server directly."""
        run_twill()


__all__ = ["TwillMixin"]
