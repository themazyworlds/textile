"""
Twill Command Definition (`textile twill`).
"""

from textile.core.cli.commands.twill.handler import run_twill_handler
from textile.core.cli.quill import quill


@quill.command("twill")
def cmd_twill():
    """Launch official Twill / MCP stdio server."""
    run_twill_handler()
