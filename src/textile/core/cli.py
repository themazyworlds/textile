"""
Textile Command-Line Interface (CLI).
Provides rich discovery, parameter schema help, execution routing, and diagnostic controls.
"""

import argparse
import difflib
import json
import sys
from typing import Any, Dict, List, Optional

from rich import box
from rich.console import Console
from rich.table import Table
from rich.tree import Tree

from textile.core.loom import loom
from textile.core.seams import seams
from textile.core.skein import skein

console = Console()


def render_table(
    title: Optional[str],
    columns: List[Dict[str, Any]],
    rows: List[List[Any]],
) -> None:
    """Render a tabular dataset cleanly using Rich Table."""
    if not rows:
        return

    table = Table(
        title=title,
        box=box.SIMPLE_HEAD,
        show_edge=False,
        header_style="bold cyan",
        pad_edge=False,
    )
    for col in columns:
        table.add_column(
            col["name"],
            style=col.get("style", "white"),
            justify=col.get("justify", "left"),
            width=col.get("width"),
        )
    for row in rows:
        table.add_row(*[str(cell) for cell in row])
    console.print(table)


def _layer_info(layer: int) -> Dict[str, Any]:
    if layer >= 1000:
        return {"level": 5, "name": "User Override"}
    elif layer >= 150:
        return {"level": 4, "name": "Session Manager"}
    elif layer >= 100:
        return {"level": 3, "name": "Compositor / DE"}
    elif layer >= 50:
        return {"level": 2, "name": "Desktop Protocol"}
    else:
        return {"level": 1, "name": "Core POSIX"}


def cmd_skein(args):
    """Inspect and manage the Skein yarn lifecycle and discovery registry."""
    skein.initialize()

    action = getattr(args, "action", None)
    yarn_target = getattr(args, "yarn_target", None)

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
        console.print(f"  [bold white]✓[/bold white] Toggled yarn [bold white]{yarn_target}[/bold white] to {state_str}.")
        return

    cols = [
        {"name": "Publisher", "style": "bold magenta"},
        {"name": "Yarn", "style": "bold cyan"},
        {"name": "Version", "justify": "center", "style": "dim"},
        {"name": "Layer", "justify": "center"},
        {"name": "Enabled", "justify": "center"},
        {"name": "Available", "justify": "center"},
        {"name": "Description", "style": "dim"},
    ]
    rows = []
    for name, yarn in sorted(skein.all_yarns.items(), key=lambda x: (-x[1].layer, x[1].name)):
        is_en = skein.is_enabled(name)
        en_str = "[green]YES[/green]" if is_en else "[red]NO[/red]"
        try:
            is_av = yarn.is_available()
            av_str = "[green]YES[/green]" if is_av else "[yellow]NO[/yellow]"
        except Exception:
            av_str = "[red]ERR[/red]"

        pub = getattr(yarn, "publisher", "") or "textile"
        rows.append([
            pub,
            yarn.name,
            getattr(yarn, "version", "1.0.0"),
            str(getattr(yarn, "layer", 10)),
            en_str,
            av_str,
            getattr(yarn, "description", ""),
        ])

    console.print(
        f"\n  [bold bright_cyan]textile skein[/bold bright_cyan] [dim]• Yarn Registry & Lifecycle Manager • {len(skein.all_yarns)} discovered yarns[/dim]\n"
    )
    render_table(None, cols, rows)
    console.print()


def cmd_loom(args):
    """List all active desktop yarns and strands in a minimal tree hierarchy."""
    loom.initialize()
    filter_yarn = getattr(args, "yarn", None)

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

    console.print(f"\n  [bold bright_cyan]textile loom[/bold bright_cyan] [dim]• {len(sorted_yarns)} active yarns • {total_strands} registered strands[/dim]\n")

    for yarn in sorted_yarns:
        strands = yarns_map[yarn]
        layer_info = _layer_info(yarn.layer)
        yarn_tree = Tree(
            f"[bold white]{yarn.name}[/bold white] [dim]v{yarn.version}[/dim] "
            f"• [dim magenta]{layer_info['name']}[/dim magenta] [dim](layer {yarn.layer})[/dim]",
            guide_style="dim cyan",
        )
        for t in sorted(strands, key=lambda x: x.name):
            is_overridden, active_name, cap_id = loom.get_strand_override_status(t, yarn)
            req_args = f" [dim green]({', '.join(t.required)})[/dim green]" if t.required else ""
            if is_overridden:
                reason = f" via '{cap_id}'" if cap_id else ""
                override_str = f" [dim yellow](overridden by [bold cyan]{active_name}[/bold cyan]{reason})[/dim yellow]"
                yarn_tree.add(f"[strike dim red]{t.name}[/strike dim red]{req_args}{override_str}")
            else:
                yarn_tree.add(f"[cyan]{t.name}[/cyan]{req_args}")
        console.print(yarn_tree)
        console.print()
    console.print("[dim]Run [bold yellow]textile help <strand_name>[/bold yellow] for parameter details.[/dim]\n")


def cmd_layers(args):
    """List all active strands organized by layer hierarchy (outermost / highest override authority first)."""
    loom.initialize()
    filter_level = getattr(args, "layer", None)

    cols = [
        {"name": "Level", "justify": "center"},
        {"name": "Layer Name", "style": "bold magenta"},
        {"name": "Yarn", "style": "bold cyan"},
        {"name": "Strand", "style": "bold white"},
        {"name": "Capability", "style": "dim yellow"},
        {"name": "Status", "justify": "center"},
    ]
    rows = []

    skein.initialize()
    all_yarns_sorted = sorted(skein.all_yarns.values(), key=lambda p: (-p.layer, p.name))
    for yarn in all_yarns_sorted:
        layer_info = _layer_info(yarn.layer)
        if filter_level and layer_info["level"] != filter_level:
            continue

        for t in yarn.get_strands():
            is_overridden, active_name, cap_id = loom.get_strand_override_status(t, yarn)
            status_str = f"[strike dim red]Overridden by {active_name}[/strike dim red]" if is_overridden else "[green]ACTIVE[/green]"
            cap_str = cap_id or "-"
            rows.append([
                str(layer_info["level"]),
                layer_info["name"],
                yarn.name,
                t.name,
                cap_str,
                status_str,
            ])

    render_table("Textile Layer Hierarchy (Outermost / Highest Authority First)", cols, rows)
    console.print()


def cmd_twill(args):
    """Launch official Twill / MCP stdio server."""
    from textile.core.twill import run_twill
    run_twill()


def cmd_weave(args):
    """Launch Weave real-time voice & desktop companion."""
    from textile.yarns.weave import run_voice_agent
    mode = "dev" if getattr(args, "dev", False) else ("start" if getattr(args, "start_worker", False) else "console")
    run_voice_agent(
        mode=mode,
        model=getattr(args, "model", "gemini-3.8-live"),
        voice=getattr(args, "voice", "Puck"),
        text_mode=getattr(args, "text_mode", False),
    )


def cmd_canvas(args):
    """Control the Quickshell Canvas Face UI and dynamic mood engine."""
    from textile.yarns.compositor.canvas import Canvas
    action = getattr(args, "action", "status") or "status"
    target = getattr(args, "target", None)
    canvas_yarn = Canvas()

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
    elif action == "status":
        state = canvas_yarn.canvas_get_state()
        running_str = "[bold green]RUNNING[/bold green]" if state.get("is_running") else "[dim red]STOPPED[/dim red]"
        console.print(f"\n  [bold bright_cyan]Textile Canvas[/bold bright_cyan] [dim]• Status:[/dim] {running_str}")
        console.print(f"  [dim]Mood:[/dim] [bold cyan]{state.get('mood')}[/bold cyan] [dim]• Expression:[/dim] [bold magenta]{state.get('expression')}[/bold magenta]")
        console.print(f"  [dim]Talking:[/dim] {state.get('is_talking')} [dim]• Listening:[/dim] {state.get('is_listening')}\n")


def cmd_seams(args):
    """Run comprehensive yarn integrity and health diagnostics."""
    loom.initialize()
    report = seams.audit_all()

    if getattr(args, "json_output", False):
        print(json.dumps(report, indent=2))
        return

    summary = report.get("summary", {})
    health = report.get("overall_health", "healthy").upper()
    color = "green" if health == "HEALTHY" else ("yellow" if health == "DEGRADED" else "red")

    active_p = summary.get("healthy_yarns", 0)
    total_p = summary.get("total_yarns", 0)
    healthy_p = summary.get("healthy_yarns", 0)
    degraded_p = summary.get("degraded_yarns", 0)
    critical_p = summary.get("critical_yarns", 0)
    strands_cnt = summary.get("total_active_strands", 0)

    console.print(
        f"\n  [bold bright_cyan]textile seams[/bold bright_cyan] [dim]•[/dim] "
        f"[bold {color}]{health}[/bold {color}] [dim]• {active_p}/{total_p} yarns active "
        f"({healthy_p} healthy, {degraded_p} degraded, {critical_p} critical) • {strands_cnt} strands[/dim]\n"
    )

    cols = [
        {"name": "Yarn", "style": "bold cyan"},
        {"name": "Layer", "justify": "center"},
        {"name": "Status", "justify": "center"},
        {"name": "Dependencies", "style": "dim"},
        {"name": "Strands", "justify": "right"},
    ]
    rows = []
    for p in report.get("yarns", []):
        p_health = p["health"].upper()
        p_color = "green" if p_health == "HEALTHY" else ("yellow" if p_health == "DEGRADED" else ("blue" if p_health == "DISABLED" else "red"))
        dep_str = ", ".join([f"{'[green]' if d['satisfied'] else '[red]'}{d['target']}[/]" for d in p.get("dependencies", [])]) or "[dim]None[/dim]"
        rows.append([p["name"], str(p.get("layer", 10)), f"[{p_color}]{p_health}[/{p_color}]", dep_str, str(p["strands_count"])])

    render_table(None, cols, rows)
    console.print()


def cmd_call(args):
    """Execute any Textile strand directly with positional or key=value arguments."""
    loom.initialize()
    strand_name = getattr(args, "strand_name", "")
    if not strand_name:
        console.print("[bold red]Error:[/bold red] No strand name specified.")
        return

    strand = loom.get_strand(strand_name)
    if not strand:
        all_strand_names = list(loom._strand_to_yarn.keys())
        matches = difflib.get_close_matches(strand_name, all_strand_names, n=3, cutoff=0.5)
        console.print(f"\n[bold red]Error:[/bold red] Strand '[bold]{strand_name}[/bold]' not found.")
        if matches:
            console.print(f"[dim]Did you mean:[/dim] [cyan]{', '.join(matches)}[/cyan] ?\n")
        return

    parsed_args = {}
    if getattr(args, "json_args", None):
        try:
            parsed_args = json.loads(args.json_args)
        except Exception as je:
            console.print(f"[bold red]Error parsing JSON arguments:[/bold red] {je}")
            return
    else:
        extra_args = getattr(args, "extra_args", [])
        param_names = list(strand.parameters.keys()) if strand.parameters else list(strand.required)
        pos_idx = 0
        for item in extra_args:
            if "=" in item:
                k, v = item.split("=", 1)
                parsed_args[k.strip()] = v.strip()
            else:
                while pos_idx < len(param_names) and param_names[pos_idx] in parsed_args:
                    pos_idx += 1
                if pos_idx < len(param_names):
                    parsed_args[param_names[pos_idx]] = item
                    pos_idx += 1

    result = loom.execute_strand(strand_name, parsed_args)
    print(result)


def cmd_help_target(args, parser=None):
    """Display detailed parameter schema and help for a specific strand or yarn."""
    loom.initialize()
    target = getattr(args, "target", None)
    if not target:
        if parser:
            parser.print_help()
        return

    target_clean = target.strip()
    skein.initialize()

    # Check if target is a Yarn
    if target_clean in skein.all_yarns:
        yarn = skein.all_yarns[target_clean]
        layer_info = _layer_info(yarn.layer)
        is_active = target_clean in loom.active_yarns

        status_str = "[green]ACTIVE[/green]" if is_active else "[red]INACTIVE[/red]"
        console.print(f"\n  [bold cyan]{yarn.name}[/bold cyan] [dim]v{yarn.version}[/dim] • {status_str}")
        console.print(f"  [dim]{yarn.description}[/dim]")
        console.print(f"  [dim]Layer:[/dim] [magenta]{layer_info['name']}[/magenta] [dim](Layer: {yarn.layer})[/dim]\n")

        strands = yarn.get_strands()
        if strands:
            cols = [
                {"name": "Strand", "style": "bold white"},
                {"name": "Required Parameters", "style": "dim green"},
                {"name": "Description", "style": "dim"},
            ]
            rows = []
            for t in strands:
                req = ", ".join(t.required) if t.required else "-"
                rows.append([t.name, req, t.description])
            render_table("Provided Strands", cols, rows)
        console.print()
        return

    # Check if target is a Strand
    strand = loom.get_strand(target_clean)
    if not strand:
        all_strand_names = list(loom._strand_to_yarn.keys())
        matches = difflib.get_close_matches(target_clean, all_strand_names, n=3, cutoff=0.5)
        console.print(f"\n[bold red]Error:[/bold red] Strand or yarn '[bold]{target_clean}[/bold]' not found.")
        if matches:
            console.print(f"[dim]Did you mean:[/dim] [cyan]{', '.join(matches)}[/cyan] ?\n")
        else:
            console.print("[dim]Run [bold]textile loom[/bold] to inspect all available strands.[/dim]\n")
        return

    yarn = loom._strand_to_yarn[target_clean]
    is_overridden, active_name, cap_id = loom.get_strand_override_status(strand, yarn)

    console.print(f"\n  [bold cyan]{strand.name}[/bold cyan] [dim]• Provider:[/dim] [bold white]{yarn.name}[/bold white] [dim](v{yarn.version})[/dim]")
    console.print(f"  [dim]{strand.description}[/dim]\n")

    if is_overridden:
        console.print(f"  [bold yellow]⚠️  Notice:[/bold yellow] This strand is currently overridden by [bold cyan]{active_name}[/bold cyan] via capability [magenta]'{cap_id}'[/magenta].\n")

    cols = [
        {"name": "Parameter", "style": "bold green"},
        {"name": "Type", "style": "magenta"},
        {"name": "Required", "justify": "center"},
        {"name": "Allowed / Enum Options", "style": "yellow"},
        {"name": "Description", "style": "dim"},
    ]
    rows = []
    params = strand.parameters or {}
    for p_name, p_spec in params.items():
        is_req = "[bold red]YES[/bold red]" if p_name in strand.required else "[dim]no[/dim]"
        p_type = p_spec.get("type", "string")
        enum_opts = ", ".join(f"'{e}'" for e in p_spec.get("enum", [])) if "enum" in p_spec else "-"
        p_desc = p_spec.get("description", "")
        rows.append([p_name, p_type, is_req, enum_opts, p_desc])

    render_table("Parameter Schema", cols, rows)
    console.print()


def main():
    parser = argparse.ArgumentParser(
        prog="textile",
        description="Textile • Linux Desktop Intelligence & Automation Fabric with Skein, Loom & Twill (MCP)"
    )
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # 1. Skein (Lifecycle & Discovery Registry)
    p_skein = subparsers.add_parser(
        "skein",
        help="Manage yarn discovery, registry, publishers, and enable/disable states"
    )
    p_skein.add_argument("action", type=str, nargs="?", choices=["enable", "disable", "toggle", "list"], default="list", help="Action to perform on yarn")
    p_skein.add_argument("yarn_target", type=str, nargs="?", help="Target yarn name to enable/disable/toggle")
    p_skein.set_defaults(func=cmd_skein)

    # 2. Loom (Registered Strands & Capabilities)
    p_loom = subparsers.add_parser(
        "loom",
        help="Inspect The Loom: list all active yarns, registered strands, and parameter schemas"
    )
    p_loom.add_argument("--yarn", type=str, help="Filter strands by yarn name")
    p_loom.set_defaults(func=cmd_loom)

    # 3. Layers (Layer Hierarchy 10 -> 150)
    p_layers = subparsers.add_parser(
        "layers",
        help="List all active strands organized by layer hierarchy (outermost / highest override authority first)"
    )
    p_layers.add_argument(
        "--layer", type=int, choices=[1, 2, 3, 4, 5],
        help="Filter to a specific layer level (1=Core POSIX … 5=User Override)"
    )
    p_layers.set_defaults(func=cmd_layers)

    # 4. Twill (MCP Server)
    p_twill = subparsers.add_parser("twill", help="Run Textile Twill (MCP) stdio server")
    p_twill.set_defaults(func=cmd_twill)

    # 5. Weave (Voice & Real-Time Companion)
    p_weave = subparsers.add_parser(
        "weave",
        help="Launch Textile Weave real-time conversational & desktop companion"
    )
    p_weave.add_argument("--text", dest="text_mode", action="store_true", help="Start in text keyboard mode instead of voice audio mode")
    p_weave.add_argument("--dev", action="store_true", help="Run LiveKit Agent in development worker mode")
    p_weave.add_argument("--start", dest="start_worker", action="store_true", help="Run LiveKit Agent in production worker mode")
    p_weave.add_argument("--voice", type=str, default="Puck", help="Gemini Live voice personality (default: Puck)")
    p_weave.add_argument("--model", type=str, default="gemini-3.8-live", help="Gemini Live model name (default: gemini-3.8-live)")
    p_weave.set_defaults(func=cmd_weave)

    # 6. Canvas (Quickshell Emotive Face UI)
    p_canvas = subparsers.add_parser(
        "canvas",
        help="Control the Quickshell Canvas Face UI and dynamic mood engine"
    )
    p_canvas.add_argument("action", type=str, nargs="?", choices=["launch", "close", "mood", "expression", "talk", "listen", "status"], default="status", help="Canvas action")
    p_canvas.add_argument("target", type=str, nargs="?", help="Mood name, expression name, or on/off flag")
    p_canvas.set_defaults(func=cmd_canvas)

    # 7. Seams (Health Diagnostics & Dependency Audit)
    p_seams = subparsers.add_parser(
        "seams",
        help="Run Seams diagnostics: yarn integrity, system health, and dependency audit"
    )
    p_seams.add_argument("--json", dest="json_output", action="store_true", help="Output audit report as JSON")
    p_seams.set_defaults(func=cmd_seams)

    # 8. Call (Direct Strand Execution)
    p_call = subparsers.add_parser("call", help="Execute any Textile strand directly (e.g. textile call wayland_clipboard_set text=hi)")
    p_call.add_argument("strand_name", type=str, help="Name of the strand to execute (e.g. wayland_clipboard_set, run_command)")
    p_call.add_argument("extra_args", nargs="*", help="Arguments for the strand (key=val pairs or positional string)")
    p_call.add_argument("--json", dest="json_args", type=str, help="JSON string of strand arguments")
    p_call.set_defaults(func=cmd_call)

    # 9. Help (Parameter Schema & Target Inspection)
    p_help = subparsers.add_parser("help", help="Display detailed parameter schema and help for a specific strand or yarn")
    p_help.add_argument("target", type=str, nargs="?", help="Name of strand or yarn to inspect")
    p_help.set_defaults(func=lambda a: cmd_help_target(a, parser))

    args = parser.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
