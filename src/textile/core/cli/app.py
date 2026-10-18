"""
Textile Engine CLI App Definition.
"""

import typer

app = typer.Typer(
    name="textile",
    help="Textile Linux Desktop AI Engine CLI - High performance desktop capabilities and IPC bus.",
    add_completion=True,
    no_args_is_help=True,
)

__all__ = ["app"]
