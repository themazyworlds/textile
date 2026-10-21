"""
Inspect Command Handler.
Reflects strand schema, parameters, and documentation.
"""

import typer

from textile.cli.ui import Column, console, print_table
lazy from textile.core.loom.mesh import loom


def inspect_strand_handler(strand_name: str) -> None:
    """Inspect detailed parameter schema and help for a specific strand."""
    target = loom.get_strand(strand_name)

    if not target:
        console.print(f"[bold red]Strand '{strand_name}' not found.[/bold red]")
        raise typer.Exit(code=1)

    console.print(
        f"\n  [bold bright_cyan]Strand Details[/bold bright_cyan] [dim]•[/dim] [bold white]{target.name}[/bold white]\n"
    )
    console.print(f"  [bold white]Tier:[/bold white] {target.tier}")
    console.print(f"  [bold white]Description:[/bold white] {target.description or '—'}\n")

    if params := target.parameters or {}:
        rows = [
            (p_name, str(p_info.get("type", "any")), str(p_info.get("description", "")))
            for p_name, p_info in sorted(params.items())
        ]
        print_table(
            columns=[
                Column("Parameter", style="bold cyan"),
                Column("Type", style="green"),
                Column("Description", style="dim"),
            ],
            rows=rows,
        )
