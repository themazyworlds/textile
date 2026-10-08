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
    header_title: str | None = None,
    subtitle: str | None = None,
    columns: Sequence[Column | str] = (),
    rows: Sequence[Sequence[Any]] = (),
    spacing: bool = True,
) -> Table:
    """Build a unified, sleek, borderless-column Rich Table with consistent typography and styling."""
    if header_title:
        sub_str = f" [dim]• {subtitle}[/dim]" if subtitle else ""
        console.print(f"\n  [bold bright_cyan]{header_title}[/bold bright_cyan]{sub_str}\n")

    table = Table(
        box=box.SIMPLE_HEAD,
        border_style="dim",
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

    num_rows = len(rows)
    for idx, row in enumerate(rows):
        table.add_row(*(str(c) if c is not None else "" for c in row))
        if spacing and idx < num_rows - 1:
            table.add_row()

    return table


def print_table(
    header_title: str | None = None,
    subtitle: str | None = None,
    columns: Sequence[Column | str] = (),
    rows: Sequence[Sequence[Any]] = (),
    spacing: bool = True,
) -> Panel:
    """Create and immediately print a unified Rich Panel table to the console."""
    table = create_table(
        header_title=header_title,
        subtitle=subtitle,
        columns=columns,
        rows=rows,
        spacing=spacing,
    )
    panel = Panel(table, box=box.ROUNDED, border_style="dim", expand=False, padding=(0, 0))
    console.print(panel)
    return panel
