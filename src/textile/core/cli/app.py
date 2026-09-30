"""
Textile Engine CLI App, Shared Console, and Base Models.
"""

import time
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


class SeamsSummaryModel(BaseModel):
    overall_health: str = Field(..., description="Overall engine health status")
    total_yarns: int = Field(0, description="Total discovered yarns")
    healthy_yarns: int = Field(0, description="Healthy active yarns")
    degraded_yarns: int = Field(0, description="Degraded yarns")
    critical_yarns: int = Field(0, description="Critical failed yarns")
    total_active_strands: int = Field(0, description="Total active executable strands")


class SeamsAuditReportModel(BaseModel):
    timestamp: float = Field(default_factory=time.time)
    overall_health: str
    summary: SeamsSummaryModel
    yarns: list[dict[str, Any]] = Field(default_factory=list)


class TapestryStateModel(BaseModel):
    engine: dict[str, Any] = Field(default_factory=dict)
    sensory: dict[str, Any] = Field(default_factory=dict)
