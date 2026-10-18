"""
Twill Command Handler.
Launches official Twill Model Context Protocol (MCP) server over stdio.
"""

lazy from textile.core.orchestration import twill


def run_twill_handler() -> None:
    """Launch official Twill / MCP stdio server."""
    twill.run_twill()
