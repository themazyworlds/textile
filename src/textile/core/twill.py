"""
Twill - High-Speed Model Context Protocol (MCP) & IPC Interconnect Fabric for Textile.
Provides standard MCP stdio JSON-RPC tool/strand dispatching aggregated across all active yarns.
"""

import asyncio
from typing import List, Optional

import mcp.types as types
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server

from textile.core.loom import loom


def create_twill_server() -> Server:
    """Create and configure official Twill / MCP Server with yarn strand dispatchers."""
    loom.initialize()
    instructions = loom.get_fabric_instructions()
    app = Server("textile", instructions=instructions)

    @app.list_prompts()
    async def handle_list_prompts() -> List[types.Prompt]:
        return [
            types.Prompt(
                name="textile_system_contract",
                description="Textile Desktop Fabric active yarn contracts, persona guidelines, and semantic streaming tags.",
            )
        ]

    @app.get_prompt()
    async def handle_get_prompt(name: str, arguments: dict | None = None) -> types.GetPromptResult:
        if name == "textile_system_contract":
            return types.GetPromptResult(
                description="Textile Desktop Fabric Active System Contract",
                messages=[
                    types.PromptMessage(
                        role="user",
                        content=types.TextContent(
                            type="text",
                            text=loom.get_fabric_instructions(),
                        ),
                    )
                ],
            )
        raise ValueError(f"Unknown prompt: {name}")

    @app.list_tools()
    async def handle_list_tools() -> List[types.Tool]:
        tools: List[types.Tool] = []
        for strand_def in loom.get_mcp_definitions():
            tools.append(
                types.Tool(
                    name=strand_def["name"],
                    description=strand_def.get("description", ""),
                    inputSchema=strand_def.get("inputSchema", {"type": "object", "properties": {}}),
                )
            )
        return tools

    @app.call_tool()
    async def handle_call_tool(name: str, arguments: dict | None) -> List[types.TextContent]:
        try:
            res_text = await loom.execute_strand_async(name, arguments or {})
            return [types.TextContent(type="text", text=str(res_text))]
        except Exception as e:
            return [types.TextContent(type="text", text=f"Strand execution error: {e}")]

    return app


import sys


async def run_twill_async():
    """Run standard IO Twill server transport using official MCP SDK."""
    if sys.stdin.isatty():
        sys.stderr.write("⚡ Textile Twill • Model Context Protocol (MCP) server listening on stdio (JSON-RPC)...\n")
        sys.stderr.write("   Ready for connections from MCP clients (Claude, Antigravity, Cursor, etc.)\n")
        sys.stderr.write("   Press Ctrl+C to terminate.\n")
        sys.stderr.flush()

    app = create_twill_server()
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options(),
        )


def run_twill():
    """Main entry point for running textile Twill stdio server."""
    try:
        asyncio.run(run_twill_async())
    except KeyboardInterrupt:
        if sys.stdin.isatty():
            sys.stderr.write("\n⚡ Textile Twill server stopped.\n")
            sys.stderr.flush()


if __name__ == "__main__":
    run_twill()
