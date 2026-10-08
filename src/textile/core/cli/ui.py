"""
Textile CLI Unified UI and Table Rendering Helpers.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal

from rich import box
from rich.panel import Panel
from rich.table import Table

from textile.core.cli.app import console

JustifyType = Literal["default", "left", "center", "right", "full"]


@dataclass
class Column:
    header: str
    style: str | None = None
    justify: JustifyType = "left"
    width: int | None = None
    no_wrap: bool = False


def create_table(
    columns: Sequence[Column | str] = (),
    rows: Sequence[Sequence[Any]] = (),
    show_header: bool = False,
) -> Table:
    """Build a compact, headerless/borderless Rich Table for Typer-style panels."""
    table = Table(
        box=None,
        show_header=show_header,
        header_style="bold bright_cyan",
        show_edge=False,
        padding=(0, 2),
    )

    for col in columns:
        if isinstance(col, Column):
            table.add_column(
                col.header,
                style=col.style,
                justify=col.justify,
                width=col.width,
                no_wrap=col.no_wrap,
            )
        else:
            table.add_column(str(col))

    for row in rows:
        table.add_row(*(str(c) if c is not None else "" for c in row))

    return table


def print_table(
    header_title: str | None = None,
    subtitle: str | None = None,
    columns: Sequence[Column | str] = (),
    rows: Sequence[Sequence[Any]] = (),
    show_header: bool = False,
) -> Panel:
    """Create and immediately print a unified Typer-style Rich Panel table to the console."""
    table = create_table(
        columns=columns,
        rows=rows,
        show_header=show_header,
    )
    title_str = f"[bold bright_cyan]{header_title}[/bold bright_cyan]" if header_title else None
    if title_str and subtitle:
        title_str += f" [dim]• {subtitle}[/dim]"

    panel = Panel(
        table,
        title=title_str,
        title_align="left",
        box=box.ROUNDED,
        border_style="dim",
        expand=False,
        padding=(0, 0),
    )
    console.print(panel)
    return panel
