"""
Textile Engine CLI App, Shared Console, and Base Models.
"""

import typer
from rich.console import Console

from textile.core.orchestration.skein import skein

console = Console()

app = typer.Typer(
    name="textile",
    help="Textile Linux Desktop AI Engine CLI - High performance desktop capabilities and IPC bus.",
    add_completion=True,
    no_args_is_help=True,
)


def ensure_initialized() -> None:
    """Ensure engine registry and Skein discovery are initialized."""
    skein.initialize()
