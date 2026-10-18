"""
Inspect Command Definition (`quill inspect`).
"""

import typer

from textile.cli.commands.inspect.handler import inspect_strand_handler
from textile.cli.quill import quill


@quill.command("inspect")
def inspect_strand(
    strand_name: str = typer.Argument(..., help="Name of strand to inspect parameter schema"),
):
    """Inspect detailed parameter schema and help for a specific strand."""
    inspect_strand_handler(strand_name)
