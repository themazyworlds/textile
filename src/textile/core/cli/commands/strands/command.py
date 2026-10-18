"""
Strands Command Definition (`textile strands`).
"""

import typer

from textile.core.cli.commands.strands.handler import list_strands_handler
from textile.core.cli.quill import quill


@quill.command("strands")
def list_strands(
    filter_query: str | None = typer.Argument(None, help="Optional filter string for strand names or descriptions"),
    tier: str | None = typer.Option(
        None,
        "--tier",
        "-t",
        help="Filter strands by capability tier (observe, interact, mutate, privileged, system_exec)",
    ),
):
    """List all registered and executable Textile Strands."""
    list_strands_handler(filter_query=filter_query, tier=tier)
