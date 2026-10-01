"""
Twill - High-Speed Model Context Protocol (MCP) & IPC Interconnect Fabric for Textile.
Provides standard MCP stdio JSON-RPC tool/strand dispatching aggregated across all active yarns.
"""

import asyncio
import os
import sys

from mcp import types
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server

from textile.core.definitions.errors import SAFE_EXCEPTIONS
from textile.core.orchestration.instructions import fabric_instructions
from textile.core.orchestration.loom import loom


def create_twill_server() -> Server:
    """Create and configure official Twill / MCP Server with yarn strand dispatchers."""
    loom.initialize()
    instructions = fabric_instructions.build_instructions(loom.active_yarns)
    app = Server("textile", instructions=instructions)

    @app.list_prompts()
    async def handle_list_prompts() -> list[types.Prompt]:
        return [
            types.Prompt(
                name="textile_system_instructions",
                description=(
                    "Textile Desktop Fabric security governance, capability tiers, and visual OTP confirmation."
                ),
            )
        ]

    @app.get_prompt()
    async def handle_get_prompt(name: str, arguments: dict | None = None) -> types.GetPromptResult:
        if name in {"textile_system_instructions", "textile_system_contract"}:
            return types.GetPromptResult(
                description="Textile Desktop Fabric Active System Instructions",
                messages=[
                    types.PromptMessage(
                        role="user",
                        content=types.TextContent(
                            type="text",
                            text=fabric_instructions.build_instructions(loom.active_yarns),
                        ),
                    )
                ],
            )
        raise ValueError(f"Unknown prompt: {name}")

    @app.list_tools()
    async def handle_list_tools() -> list[types.Tool]:
        return [
            types.Tool(
                name=strand_def["name"],
                description=strand_def.get("description", ""),
                inputSchema=strand_def.get("inputSchema", {"type": "object", "properties": {}}),
            )
            for strand_def in fabric_instructions.get_mcp_definitions(loom.get_all_strands())
        ]

    @app.call_tool()
    async def handle_call_tool(name: str, arguments: dict | None) -> list[types.TextContent]:
        try:
            args_dict = dict(arguments) if arguments else {}
            otp_val = args_dict.pop("otp", None)
            effective_caller = os.getenv("TEXTILE_CALLER", "twill_mcp")
            res_text = await loom.execute(name, args_dict, caller=effective_caller, otp=otp_val)
            return [types.TextContent(type="text", text=str(res_text))]
        except SAFE_EXCEPTIONS as e:
            return [types.TextContent(type="text", text=f"Strand execution error: {e}")]

    return app


async def run_twill_async():
    """Run standard IO Twill server transport using official MCP SDK."""
    if sys.stdin.isatty():
        sys.stderr.write("   Textile Twill • Model Context Protocol (MCP) server listening on stdio (JSON-RPC)...\n")
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
