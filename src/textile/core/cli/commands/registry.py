"""
Textile CLI Registry, Health Audit, and Blackboard Diagnostics Commands.
"""

import typer
from rich import box
from rich.table import Table
from rich.tree import Tree

from textile.core.cli.app import (
    SeamsAuditReportModel,
    SeamsSummaryModel,
    TapestryStateModel,
    app,
    console,
    ensure_initialized,
)
from textile.core.contracts.layers import get_layer_info
from textile.core.orchestration.loom import loom
from textile.core.orchestration.skein import skein
from textile.core.telemetry.seams import seams
from textile.core.telemetry.tapestry import core_tapestry, sensory_tapestry


@app.command("skein")
def cmd_skein(
    action: str | None = typer.Argument(None, help="Action to perform: enable, disable, toggle"),
    yarn_target: str | None = typer.Argument(None, help="Target yarn name for enable/disable/toggle"),
):
    """Inspect and manage the Skein yarn lifecycle and discovery registry."""
    ensure_initialized()

    if action == "enable" and yarn_target:
        skein.set_yarn_enabled(yarn_target, True)
        loom._rebuild_active()
        console.print(f"  [bold green]✓[/bold green] Enabled yarn [bold white]{yarn_target}[/bold white].")
        return
    elif action == "disable" and yarn_target:
        skein.set_yarn_enabled(yarn_target, False)
        loom._rebuild_active()
        console.print(f"  [bold yellow]✓[/bold yellow] Disabled yarn [bold white]{yarn_target}[/bold white].")
        return
    elif action == "toggle" and yarn_target:
        state = skein.toggle_yarn(yarn_target)
        loom._rebuild_active()
        state_str = "[bold green]enabled[/bold green]" if state else "[bold yellow]disabled[/bold yellow]"
        console.print(
            f"  [bold white]✓[/bold white] Toggled yarn [bold white]{yarn_target}[/bold white] to {state_str}."
        )
        return

    table = Table(
        title=f"Textile Skein Yarn Registry ({len(skein.all_yarns)} discovered yarns)",
        box=box.SIMPLE_HEAD,
        show_edge=False,
        header_style="bold cyan",
    )
    table.add_column("Yarn", style="bold cyan")
    table.add_column("Layer", justify="center")
    table.add_column("Enabled", justify="center")
    table.add_column("Available", justify="center")
    table.add_column("Description", style="dim")

    for name, yarn in sorted(skein.all_yarns.items(), key=lambda x: (-x[1].layer, x[1].name)):
        is_en = skein.is_enabled(name)
        en_str = "[green]YES[/green]" if is_en else "[red]NO[/red]"
        try:
            is_av = yarn.is_available()
            av_str = "[green]YES[/green]" if is_av else "[yellow]NO[/yellow]"
        except (AttributeError, TypeError, ValueError, KeyError, OSError, RuntimeError):
            av_str = "[red]ERR[/red]"

        layer_name = get_layer_info(yarn.layer).name
        table.add_row(yarn.name, f"{yarn.layer} ({layer_name})", en_str, av_str, yarn.description or "")

    console.print(table)


@app.command("loom")
def cmd_loom(
    filter_yarn: str | None = typer.Argument(None, help="Filter strands by specific yarn name"),
):
    """List active desktop yarns and strands in a visual tree hierarchy."""
    ensure_initialized()
    loom.initialize()

    yarns_map = {}
    total_strands = 0
    for p_name, yarn_obj in loom.active_yarns.items():
        if filter_yarn and p_name != filter_yarn:
            continue
        if strands_list := yarn_obj.get_strands():
            yarns_map[yarn_obj] = strands_list
            total_strands += len(strands_list)

    sorted_yarns = sorted(yarns_map.keys(), key=lambda p: (-p.layer, p.name))
    if not sorted_yarns:
        console.print(
            f"[dim]No active yarns found{f' matching filter {filter_yarn}' if filter_yarn else ''}.[/dim]"
        )
        return

    console.print(
        f"\n  [bold bright_cyan]Textile Loom[/bold bright_cyan] "
        f"[dim]• {len(sorted_yarns)} active yarns • {total_strands} registered strands[/dim]\n"
    )

    for yarn in sorted_yarns:
        strands = yarns_map[yarn]
        yarn_tree = Tree(
            f"[bold white]{yarn.name}[/bold white] [dim]v{yarn.version}[/dim] "
            f"• [dim magenta]Layer {yarn.layer}[/dim magenta]",
            guide_style="dim cyan",
        )
        for t in sorted(strands, key=lambda x: x.name):
            is_overridden, active_name, cap_id = loom.get_strand_override_status(t, yarn)
            if is_overridden:
                yarn_tree.add(
                    f"[strike dim red]{t.name}[/strike dim red] [dim yellow](overridden by {active_name})[/dim yellow]"
                )
            else:
                yarn_tree.add(f"[cyan]{t.name}[/cyan]")
        console.print(yarn_tree)


@app.command("seams")
def cmd_seams(
    json_output: bool = typer.Option(False, "--json", help="Output audit report as Pydantic JSON"),
):
    """Run comprehensive yarn integrity and health diagnostics."""
    loom.initialize()
    report_dict = seams.audit_all()

    summary_data = report_dict.get("summary", {})
    summary_model = SeamsSummaryModel(
        overall_health=report_dict.get("overall_health", "healthy"),
        total_yarns=summary_data.get("total_yarns", 0),
        healthy_yarns=summary_data.get("healthy_yarns", 0),
        degraded_yarns=summary_data.get("degraded_yarns", 0),
        critical_yarns=summary_data.get("critical_yarns", 0),
        total_active_strands=summary_data.get("total_active_strands", 0),
    )
    audit_report = SeamsAuditReportModel(
        overall_health=report_dict.get("overall_health", "healthy"),
        summary=summary_model,
        yarns=report_dict.get("yarns", []),
    )

    if json_output:
        print(audit_report.model_dump_json(indent=2))
        return

    health = audit_report.overall_health.upper()
    color = "green" if health == "HEALTHY" else ("yellow" if health == "DEGRADED" else "red")

    console.print(
        f"\n  [bold bright_cyan]textile seams[/bold bright_cyan] [dim]•[/dim] "
        f"[bold {color}]{health}[/bold {color}] "
        f"[dim]• {summary_model.healthy_yarns}/{summary_model.total_yarns} yarns active "
        f"• {summary_model.total_active_strands} strands[/dim]\n"
    )

    table = Table(box=box.SIMPLE_HEAD, show_edge=False, header_style="bold cyan")
    table.add_column("Yarn", style="bold cyan")
    table.add_column("Layer", justify="center")
    table.add_column("Status", justify="center")
    table.add_column("Strands", justify="right")

    for p in audit_report.yarns:
        p_health = p.get("health", "healthy").upper()
        p_color = "green" if p_health == "HEALTHY" else ("yellow" if p_health == "DEGRADED" else "red")
        table.add_row(
            p.get("name", ""),
            str(p.get("layer", 10)),
            f"[{p_color}]{p_health}[/{p_color}]",
            str(p.get("strands_count", 0)),
        )

    console.print(table)


@app.command("tapestry")
def cmd_tapestry(
    json_output: bool = typer.Option(False, "--json", help="Output tapestry state as Pydantic JSON"),
):
    """Inspect engine task ledger and sensory blackboard."""
    if json_output:
        model = TapestryStateModel(
            engine=core_tapestry.get_state(),
            sensory=sensory_tapestry.get_state(),
        )
        print(model.model_dump_json(indent=2))
        return

    active = core_tapestry.get_active_tasks()
    history = core_tapestry.get_task_history(limit=15)

    table = Table(
        title=f"Core Task Ledger ({len(active)} active tasks)",
        box=box.SIMPLE_HEAD,
        show_edge=False,
        header_style="bold cyan",
    )
    table.add_column("Task ID", style="bold yellow", width=10)
    table.add_column("Strand", style="bold white", width=28)
    table.add_column("Tier", width=12)
    table.add_column("Status", width=12)

    for t in active:
        table.add_row(t["task_id"][:8], t["strand_name"], str(t.get("tier", "-")), "[bold green]RUNNING[/bold green]")
    for t in reversed(history):
        status_str = "[green]SUCCESS[/green]" if t.get("success") else "[red]FAILED[/red]"
        table.add_row(t["task_id"][:8], t["strand_name"], str(t.get("tier", "-")), status_str)

    console.print(table)
