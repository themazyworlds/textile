"""
Textile Quill - Command-Line Interface (CLI) Dispatcher & Interactive Command Driver.
"""

import typer

quill = typer.Typer(
    name="textile",
    help="Textile Linux Desktop AI Engine CLI - High performance desktop capabilities and IPC bus.",
    add_completion=True,
    no_args_is_help=True,
)

__all__ = ["quill"]
