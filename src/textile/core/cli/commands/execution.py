"""
Textile CLI Strand and Yarn Execution Commands.
"""

import json
from typing import Any

import typer

from textile.core.cli.app import app, console, ensure_initialized
from textile.core.cli.ui import Column, print_table
from textile.core.definitions.errors import StrandNotFoundError, TextileError
from textile.core.orchestration.loom import loom
from textile.core.orchestration.skein import skein


def _parse_cli_arg_val(val: str) -> Any:
    clean_val = val.strip("\"'")
    if clean_val.lower() == "true":
        return True
    if clean_val.lower() == "false":
        return False
    return clean_val


def _parse_cli_args(strand_name: str, args: list[str]) -> dict[str, Any]:
    target_strand = loom.get_strand(strand_name)
    param_names = list(target_strand.parameters.keys()) if target_strand and target_strand.parameters else []

    named_kwargs: dict[str, Any] = {}
    positional_vals: list[Any] = []

    for arg in args:
        if "=" in arg:
            k, v = arg.split("=", 1)
            named_kwargs[k] = _parse_cli_arg_val(v)
        else:
            positional_vals.append(_parse_cli_arg_val(arg))

    parsed_kwargs = named_kwargs.copy()
    pos_idx = 0
    for p_name in param_names:
        if pos_idx >= len(positional_vals):
            break
        if p_name not in parsed_kwargs:
            parsed_kwargs[p_name] = positional_vals[pos_idx]
            pos_idx += 1

    while pos_idx < len(positional_vals):
        if "target" not in parsed_kwargs and pos_idx == 0:
            parsed_kwargs["target"] = positional_vals[pos_idx]
        pos_idx += 1

    return parsed_kwargs


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
    ensure_initialized()
    strands = loom.get_all_strands()
    query = (filter_query or "").strip().lower()

    matched: list[tuple[str, str, str]] = []
    for s in strands:
        s_name = s.name
        s_tier = str(s.tier or "")
        s_cap = s.capability or ""
        s_desc = (s.description or "").splitlines()[0].strip() if s.description else ""

        if query and query not in s_name.lower() and query not in s_desc.lower() and query not in s_cap.lower():
            continue
        if tier and tier.lower() != s_tier.lower():
            continue

        matched.append((s_name, s_tier, s_desc))

    print_table(
        header_title="Textile Strands",
        subtitle=f"{len(matched)} registered strands",
        columns=[
            Column("Strand", style="bold cyan", no_wrap=True),
            Column("Tier", justify="center", no_wrap=True),
            Column("Description", style="dim"),
        ],
        rows=matched,
    )


@app.command("yarns")
def list_yarns():
    """Inspect registered Yarn modules and layer hierarchy."""
    ensure_initialized()
    yarns = sorted(skein.all_yarns.values(), key=lambda item: (-item.layer, item.name))

    rows = []
    for y in yarns:
        status_str = "[green]ACTIVE[/green]" if skein.is_enabled(y.name) else "[red]DISABLED[/red]"
        desc = (y.description or "").splitlines()[0].strip() if y.description else ""
        rows.append((y.name, str(y.layer), status_str, desc))

    print_table(
        header_title="Textile Yarns",
        subtitle=f"{len(yarns)} capability yarns",
        columns=[
            Column("Yarn", style="bold cyan", no_wrap=True),
            Column("Layer", justify="center", no_wrap=True),
            Column("Status", justify="center", no_wrap=True),
            Column("Description", style="dim"),
        ],
        rows=rows,
    )


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
    ensure_initialized()
    parsed_kwargs = {}

    if json_args:
        try:
            parsed_kwargs = json.loads(json_args)
        except json.JSONDecodeError as e:
            console.print(f"[bold red]Error parsing JSON arguments:[/bold red] {e}")
            raise typer.Exit(code=1) from e
    elif args:
        parsed_kwargs = _parse_cli_args(strand_name, args)

    try:
        res = loom.execute_sync(strand_name, parsed_kwargs)
        console.print(res)
    except TextileError as e:
        console.print(f"[bold red]{e.message}[/bold red]")
        if e.hint:
            console.print(f"[dim yellow]Hint: {e.hint}[/dim yellow]")
        raise typer.Exit(code=1) from e


@app.command("inspect")
def inspect_strand(
    strand_name: str = typer.Argument(..., help="Name of strand to inspect parameter schema"),
):
    """Inspect detailed parameter schema and help for a specific strand."""
    ensure_initialized()
    target = loom.get_strand(strand_name)

    if not target:
        all_names = [s.name for s in loom.get_all_strands()]
        err = StrandNotFoundError(strand_name, available_strands=all_names)
        console.print(f"[bold red]{err.message}[/bold red]")
        console.print(f"[dim yellow]{err.hint}[/dim yellow]")
        raise typer.Exit(code=1)

    console.print(
        f"\n  [bold bright_cyan]Strand Details[/bold bright_cyan] "
        f"[dim]•[/dim] [bold white]{target.name}[/bold white]\n"
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
