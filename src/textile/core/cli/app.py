"""
Textile Engine CLI App, Shared Console, and Base Models.
"""

from typing import Any

import typer
from pydantic import BaseModel, Field
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


class TapestryStateModel(BaseModel):
    engine: dict[str, Any] = Field(default_factory=dict)
    sensory: dict[str, Any] = Field(default_factory=dict)
