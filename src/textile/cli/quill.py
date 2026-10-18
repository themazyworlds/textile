"""
Textile Quill - Command-Line Interface (CLI) Dispatcher & Interactive Command Driver.
"""

import typer

quill = typer.Typer(
    name="quill",
    help="Quill - Interactive Command Driver for the Textile Linux Desktop AI Subsystem.",
    add_completion=True,
    no_args_is_help=True,
)

__all__ = ["quill"]
