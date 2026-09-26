"""
Textile Engine Command-Line Interface (CLI).
Provides discovery, layer hierarchy, strand inspection, execution, IPC, and health diagnostics.
"""

import importlib
import json
import time
from typing import Any

import typer
from pydantic import BaseModel, Field
from rich import box
from rich.console import Console
from rich.table import Table
from rich.tree import Tree

from textile.core.errors import StrandNotFoundError, TextileError
from textile.core.loom import loom
from textile.core.seams import seams
from textile.core.skein import skein
from textile.core.tapestry import core_tapestry, sensory_tapestry
from textile.core.twill import run_twill

console = Console()

LAYER_USER_OVERRIDE_THRESHOLD = 1000
LAYER_SESSION_MANAGER_THRESHOLD = 150
LAYER_COMPOSITOR_DE_THRESHOLD = 100
LAYER_DESKTOP_PROTOCOL_THRESHOLD = 50


def _layer_info(layer: int) -> dict[str, Any]:
    if layer >= LAYER_USER_OVERRIDE_THRESHOLD:
        return {"level": 5, "name": "User Override"}
    elif layer >= LAYER_SESSION_MANAGER_THRESHOLD:
        return {"level": 4, "name": "Session Manager"}
    elif layer >= LAYER_COMPOSITOR_DE_THRESHOLD:
        return {"level": 3, "name": "Compositor / DE"}
    elif layer >= LAYER_DESKTOP_PROTOCOL_THRESHOLD:
        return {"level": 2, "name": "Desktop Protocol"}
    else:
        return {"level": 1, "name": "Core POSIX"}


# --- Pydantic v2 Output Models for CLI Commands ---

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


def _ensure_initialized():
    skein.initialize()


app = typer.Typer(
    name="textile",
    help="Textile Linux Desktop AI Engine CLI - High performance desktop capabilities and IPC bus.",
    add_completion=True,
    no_args_is_help=True,
)


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


@app.command("skein")
def cmd_skein(
    action: str | None = typer.Argument(None, help="Action to perform: enable, disable, toggle"),
    yarn_target: str | None = typer.Argument(None, help="Target yarn name for enable/disable/toggle"),
):
    """Inspect and manage the Skein yarn lifecycle and discovery registry."""
    _ensure_initialized()

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

        table.add_row(yarn.name, str(yarn.layer), en_str, av_str, yarn.description or "")

    console.print(table)


@app.command("loom")
def cmd_loom(
    filter_yarn: str | None = typer.Argument(None, help="Filter strands by specific yarn name"),
):
    """List active desktop yarns and strands in a visual tree hierarchy."""
    _ensure_initialized()
    loom.initialize()

    yarns_map = {}
    total_strands = 0
    for p_name, yarn_obj in loom.active_yarns.items():
        if filter_yarn and p_name != filter_yarn:
            continue
        strands_list = yarn_obj.get_strands()
        if strands_list:
            yarns_map[yarn_obj] = strands_list
            total_strands += len(strands_list)

    sorted_yarns = sorted(yarns_map.keys(), key=lambda p: (-p.layer, p.name))
    if not sorted_yarns:
        console.print(f"[dim]No active yarns found{' matching filter ' + filter_yarn if filter_yarn else ''}.[/dim]")
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


@app.command("twill")
def cmd_twill():
    """Launch official Twill / MCP stdio server."""
    run_twill()


@app.command("weave")
def cmd_weave(
    dev: bool = typer.Option(False, "--dev", help="Run in dev LiveKit worker mode"),
    start_worker: bool = typer.Option(False, "--start-worker", help="Start background worker process"),
    model: str = typer.Option("gemini-3.8-live", "--model", help="Gemini Live model name"),
    voice: str = typer.Option("Puck", "--voice", help="Gemini voice name (e.g. Puck, Aoede, Charon, Fenrir, Kore)"),
    text_mode: bool = typer.Option(False, "--text", help="Run in text-only console mode"),
):
    """Launch Weave real-time voice & desktop companion."""
    mod = importlib.import_module("textile.yarns.weave.weave")
    run_voice_agent = getattr(mod, "run_voice_agent")
    mode = "dev" if dev else ("start" if start_worker else "console")
    run_voice_agent(mode=mode, model=model, voice=voice, text_mode=text_mode)


@app.command("canvas")
def cmd_canvas(
    action: str = typer.Argument("status", help="Canvas action: launch, close, mood, expression, talk, listen, status"),
    target: str | None = typer.Argument(None, help="Mood name, expression name, or on/off flag"),
):
    """Control the Quickshell Canvas Face UI and dynamic mood engine."""
    mod = importlib.import_module("textile.yarns.canvas.canvas")
    canvas_cls = getattr(mod, "Canvas")
    canvas_yarn = canvas_cls()

    if action == "launch":
        res = canvas_yarn.canvas_launch()
        console.print(f"  [bold green]✓[/bold green] {res}")
    elif action == "close":
        res = canvas_yarn.canvas_close()
        console.print(f"  [bold yellow]✓[/bold yellow] {res}")
    elif action == "mood":
        mood_name = target or "neutral"
        res = canvas_yarn.canvas_set_mood(mood_name)
        console.print(f"  [bold cyan]✓[/bold cyan] {res}")
    elif action == "expression":
        expr_name = target or "neutral"
        res = canvas_yarn.canvas_set_expression(expr_name)
        console.print(f"  [bold magenta]✓[/bold magenta] {res}")
    elif action == "talk":
        talking = target.lower() not in ("off", "false", "0", "no") if target else True
        res = canvas_yarn.canvas_set_talking(talking)
        console.print(f"  [bold white]✓[/bold white] {res}")
    elif action == "listen":
        listening = target.lower() not in ("off", "false", "0", "no") if target else True
        res = canvas_yarn.canvas_set_listening(listening)
        console.print(f"  [bold white]✓[/bold white] {res}")
    else:
        state = canvas_yarn.canvas_get_state()
        running_str = "[bold green]RUNNING[/bold green]" if state.get("is_running") else "[dim red]STOPPED[/dim red]"
        console.print(f"\n  [bold bright_cyan]Textile Canvas[/bold bright_cyan] [dim]• Status:[/dim] {running_str}")
        console.print(
            f"  [dim]Mood:[/dim] [bold cyan]{state.get('mood')}[/bold cyan] • "
            f"[dim]Expression:[/dim] [bold magenta]{state.get('expression')}[/bold magenta]"
        )


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


def main():
    app()


if __name__ == "__main__":
    main()
