"""
Twill Command Handler.
Launches official Twill Model Context Protocol (MCP) server over stdio.
"""

lazy from textile.core.twill.mesh import run_twill_async


async def run_twill_handler() -> None:
    """Launch official Twill / MCP stdio server."""
    await run_twill_async()
