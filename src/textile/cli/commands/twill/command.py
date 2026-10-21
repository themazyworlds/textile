"""
Twill Command Definition (`quill twill`).
"""

from textile.cli.quill import quill
lazy from textile.cli.commands.twill.handler import run_twill_handler


@quill.command("twill")
async def cmd_twill():
    """Launch official Twill / MCP stdio server."""
    await run_twill_handler()
