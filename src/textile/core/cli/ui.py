"""
Textile CLI Unified UI and Table Rendering Helpers.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal

from rich import box
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
) -> Table:
    """Build a unified, sleek, rounded-border Rich Table with consistent typography and styling."""
    if header_title:
        sub_str = f" [dim]• {subtitle}[/dim]" if subtitle else ""
        console.print(f"\n  [bold bright_cyan]{header_title}[/bold bright_cyan]{sub_str}\n")

    table = Table(
        box=box.ROUNDED,
        border_style="dim",
        header_style="bold bright_cyan",
        show_edge=True,
        padding=(0, 2, 1, 2),
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
) -> Table:
    """Create and immediately print a unified Rich Table to the console."""
    table = create_table(
        header_title=header_title,
        subtitle=subtitle,
        columns=columns,
        rows=rows,
    )
    console.print(table)
    return table
