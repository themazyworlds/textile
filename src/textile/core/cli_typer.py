"""
Typer-Based Modern Textile CLI Application.
Auto-discovers registered desktop yarns & strands with type coercion, parameter help, and rich tables.
"""

import json

import typer
from rich import box
from rich.console import Console
from rich.table import Table

from textile.core.errors import StrandNotFoundError, TextileError
from textile.core.loom import loom
from textile.core.skein import skein

app = typer.Typer(
    name="textile",
    help="Textile Linux Desktop AI Engine CLI - High performance desktop capabilities and IPC bus.",
    add_completion=True,
    no_args_is_help=True,
)

console = Console()


def _ensure_initialized():
    skein.initialize()


@app.command("strands")
def list_strands(
    filter_query: str | None = typer.Argument(None, help="Optional filter string for strand names or descriptions"),
    tier: str | None = typer.Option(
        None,
        "--tier",
        "-t",
        help="Filter strands by capability tier (observe, interact, mutate, privileged, system_exec)",
    ),
):
    """List all registered and executable Textile Strands."""
    _ensure_initialized()
    strands = loom.get_all_strands()
    query = (filter_query or "").strip().lower()

    table = Table(
        title="[bold cyan]Textile Registered Strands[/bold cyan]",
        box=box.SIMPLE_HEAD,
        show_edge=False,
        header_style="bold cyan",
    )
    table.add_column("Strand Name", style="bold white")
    table.add_column("Tier", style="yellow")
    table.add_column("Capability", style="dim white")
    table.add_column("Description", style="dim green")

    count = 0
    for s in strands:
        s_name = s.name
        s_tier = str(s.tier or "")
        s_cap = s.capability or "—"
        s_desc = s.description or ""

        if query and query not in s_name.lower() and query not in s_desc.lower() and query not in s_cap.lower():
            continue
        if tier and tier.lower() != s_tier.lower():
            continue

        table.add_row(s_name, s_tier, s_cap, s_desc)
        count += 1

    console.print(table)
    console.print(f"\n[bold green]Total Strands Matched:[/bold green] {count}")


@app.command("yarns")
def list_yarns():
    """Inspect registered Yarn modules and layer hierarchy."""
    _ensure_initialized()
    yarns = sorted(skein.all_yarns.values(), key=lambda item: item.layer)

    table = Table(
        title="[bold cyan]Registered Textile Capability Yarns[/bold cyan]",
        box=box.SIMPLE_HEAD,
        show_edge=False,
        header_style="bold cyan",
    )
    table.add_column("Yarn Name", style="bold white")
    table.add_column("Layer", style="magenta")
    table.add_column("Status", style="green")

    for y in yarns:
        status_str = "[bold green]Active[/bold green]" if skein.is_enabled(y.name) else "[bold red]Disabled[/bold red]"
        table.add_row(y.name, str(y.layer), status_str)

    console.print(table)


@app.command("call")
def call_strand(
    strand_name: str = typer.Argument(
        ...,
        help="Name of the strand to execute (e.g. hyprland_get_windows, clipboard_get)",
    ),
    args: list[str] = typer.Argument(None, help="Key=Value parameters (e.g. text='Hello World' target=1)"),
    json_args: str | None = typer.Option(None, "--json", "-j", help="Raw JSON string of arguments"),
):
    """Execute any registered Textile strand directly with parameter validation."""
    _ensure_initialized()
    parsed_kwargs = {}

    if json_args:
        try:
            parsed_kwargs = json.loads(json_args)
        except json.JSONDecodeError as e:
            console.print(f"[bold red]Error parsing JSON arguments:[/bold red] {e}")
            raise typer.Exit(code=1)
    elif args:
        for arg in args:
            if "=" in arg:
                k, v = arg.split("=", 1)
                clean_v = v.strip("\"'")
                if clean_v.lower() == "true":
                    parsed_kwargs[k] = True
                elif clean_v.lower() == "false":
                    parsed_kwargs[k] = False
                elif clean_v.isdigit():
                    parsed_kwargs[k] = int(clean_v)
                else:
                    parsed_kwargs[k] = clean_v
            else:
                parsed_kwargs["target"] = arg

    try:
        res = loom.execute_sync(strand_name, parsed_kwargs)
        console.print(res)
    except TextileError as e:
        console.print(f"[bold red]{e.message}[/bold red]")
        if e.hint:
            console.print(f"[dim yellow]Hint: {e.hint}[/dim yellow]")
        raise typer.Exit(code=1)


@app.command("inspect")
def inspect_strand(
    strand_name: str = typer.Argument(..., help="Name of strand to inspect parameter schema"),
):
    """Inspect detailed parameter schema and help for a specific strand."""
    _ensure_initialized()
    target = loom.get_strand(strand_name)

    if not target:
        all_names = [s.name for s in loom.get_all_strands()]
        err = StrandNotFoundError(strand_name, available_strands=all_names)
        console.print(f"[bold red]{err.message}[/bold red]")
        console.print(f"[dim yellow]{err.hint}[/dim yellow]")
        raise typer.Exit(code=1)

    console.print(f"[bold cyan]Strand:[/bold cyan] {target.name}")
    console.print(f"[bold white]Tier:[/bold white] {target.tier}")
    console.print(f"[bold white]Description:[/bold white] {target.description}")

    params = target.parameters or {}
    if params:
        table = Table(title="Parameters", box=box.SIMPLE)
        table.add_column("Parameter", style="bold white")
        table.add_column("Type", style="cyan")
        table.add_column("Description", style="dim green")
        for p_name, p_info in params.items():
            table.add_row(p_name, str(p_info.get("type", "any")), p_info.get("description", ""))
        console.print(table)


def main():
    app()


if __name__ == "__main__":
    main()
