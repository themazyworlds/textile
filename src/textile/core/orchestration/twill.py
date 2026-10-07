"""
Twill - High-Speed Model Context Protocol (MCP) & IPC Interconnect Fabric for Textile.
Provides standard MCP stdio JSON-RPC tool/strand dispatching aggregated across all active yarns.
"""

import asyncio
import os
import sys
from typing import Any

from mcp import types
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server

from textile.core.definitions.errors import SAFE_EXCEPTIONS, StrandOperationalError
from textile.core.orchestration.instructions import fabric_instructions
from textile.core.orchestration.loom import loom
from textile.core.security.context import OTPChallengeRequiredError, PolicyViolationError


def create_twill_server() -> Server:
    """Create and configure official Twill / MCP Server with yarn strand dispatchers."""
    loom.initialize()
    instructions = fabric_instructions.build_instructions(loom.active_yarns)

    async def handle_list_prompts(
        _ctx: Any, _params: types.PaginatedRequestParams | None = None
    ) -> types.ListPromptsResult:
        return types.ListPromptsResult(
            prompts=[
                types.Prompt(
                    name="textile_system_instructions",
                    description=(
                        "Textile Desktop Fabric security governance, capability tiers, and visual OTP confirmation."
                    ),
                )
            ]
        )

    async def handle_get_prompt(
        _ctx: Any, params: types.GetPromptRequestParams
    ) -> types.GetPromptResult:
        if params.name in {"textile_system_instructions", "textile_system_contract"}:
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
        raise ValueError(f"Unknown prompt: {params.name}")

    async def handle_list_tools(
        _ctx: Any, _params: types.PaginatedRequestParams | None = None
    ) -> types.ListToolsResult:
        return types.ListToolsResult(
            tools=[
                types.Tool(
                    name=strand_def["name"],
                    description=strand_def.get("description", ""),
                    input_schema=strand_def.get("input_schema")
                    or strand_def.get("inputSchema", {"type": "object", "properties": {}}),
                )
                for strand_def in fabric_instructions.get_mcp_definitions(loom.get_all_strands())
            ]
        )

    async def handle_call_tool(
        _ctx: Any, params: types.CallToolRequestParams
    ) -> types.CallToolResult:
        name = params.name
        arguments = params.arguments or {}
        try:
            args_dict = dict(arguments)
            otp_val = args_dict.pop("otp", None)
            effective_caller = os.getenv("TEXTILE_CALLER", "twill_mcp")
            res_text = await loom.execute(name, args_dict, caller=effective_caller, otp=otp_val)
            return types.CallToolResult(content=[types.TextContent(type="text", text=str(res_text))])
        except PolicyViolationError as e:
            return types.CallToolResult(
                content=[types.TextContent(type="text", text=f"Security Policy Violation: {e}")], is_error=True
            )
        except OTPChallengeRequiredError as e:
            return types.CallToolResult(content=[types.TextContent(type="text", text=str(e))], is_error=True)
        except StrandOperationalError as e:
            return types.CallToolResult(content=[types.TextContent(type="text", text=str(e))], is_error=True)
        except SAFE_EXCEPTIONS as e:
            err_msg = f"[Operational Failure] Strand '{name}' execution error: {e}"
            return types.CallToolResult(content=[types.TextContent(type="text", text=err_msg)], is_error=True)

    return Server(
        "textile",
        instructions=instructions,
        on_list_prompts=handle_list_prompts,
        on_get_prompt=handle_get_prompt,
        on_list_tools=handle_list_tools,
        on_call_tool=handle_call_tool,
    )


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
