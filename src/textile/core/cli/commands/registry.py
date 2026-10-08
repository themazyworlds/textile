"""
Textile CLI Registry, Health Audit, and Blackboard Diagnostics Commands.
"""

import shutil
import subprocess
from pathlib import Path
from typing import Any

import platformdirs
import typer
from pydantic import BaseModel
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
from textile.core.definitions.layers import get_layer_info
from textile.core.definitions.settings import _format_type_name
from textile.core.orchestration.loom import loom
from textile.core.orchestration.skein import skein
from textile.core.telemetry.auditor import audit_all
from textile.core.telemetry.blackboard import sensory_tapestry
from textile.core.telemetry.ledger import core_tapestry


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

    console.print(
        f"\n  [bold bright_cyan]Textile Skein[/bold bright_cyan] "
        f"[dim]• {len(skein.all_yarns)} capability yarns discovered[/dim]\n"
    )
    table = Table(
        box=box.ROUNDED,
        border_style="dim",
        header_style="bold bright_cyan",
        show_edge=True,
        padding=(0, 1),
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


def _parse_cli_setting_val(raw: str) -> Any:
    if raw.lower() == "true":
        return True
    if raw.lower() == "false":
        return False
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        pass
    return raw


def _render_yarn_settings_table(yarn_name: str, settings: dict[str, Any]) -> None:
    console.print(
        f"\n  [bold bright_cyan]User Settings[/bold bright_cyan] [dim]•[/dim] [bold white]{yarn_name}[/bold white]\n"
    )
    table = Table(
        box=box.ROUNDED,
        border_style="dim",
        header_style="bold bright_cyan",
        show_edge=True,
        padding=(0, 1),
    )
    table.add_column("Setting Key", style="bold cyan")
    table.add_column("Value", style="green")
    for k, v in sorted(settings.items()):
        table.add_row(k, str(v))
    console.print(table)


def _render_all_settings_table(all_settings: dict[str, Any]) -> None:
    if not all_settings:
        console.print("\n  [dim]No user overrides found in ~/.config/textile/settings.toml.[/dim]\n")
        return

    console.print(
        "\n  [bold bright_cyan]Textile User Settings[/bold bright_cyan] "
        "[dim](~/.config/textile/settings.toml)[/dim]\n"
    )
    table = Table(
        box=box.ROUNDED,
        border_style="dim",
        header_style="bold bright_cyan",
        show_edge=True,
        padding=(0, 1),
    )
    table.add_column("Yarn", style="bold cyan")
    table.add_column("Key", style="bold white")
    table.add_column("Value", style="green")

    for y_name, s_dict in sorted(all_settings.items()):
        if isinstance(s_dict, dict):
            for k, v in sorted(s_dict.items()):
                table.add_row(y_name, k, str(v))

    console.print(table)


def _render_schema_docs(yarn_name: str | None = None) -> None:
    schemas = skein.get_all_yarn_schemas()
    if yarn_name and yarn_name in schemas:
        targets = {yarn_name: schemas[yarn_name]}
    elif yarn_name:
        console.print(f"  [bold red]Error:[/bold red] Yarn '{yarn_name}' has no declared settings schema.")
        return
    else:
        targets = schemas

    for y_name, schema_or_dict in sorted(targets.items()):
        console.print(
            f"\n  [bold bright_cyan]Settings Schema[/bold bright_cyan] "
            f"[dim]•[/dim] [bold white]{y_name}[/bold white]\n"
        )
        table = Table(
            box=box.ROUNDED,
            border_style="dim",
            header_style="bold bright_cyan",
            show_edge=True,
            padding=(0, 1),
        )
        table.add_column("Setting", style="bold cyan")
        table.add_column("Type", style="dim", justify="center")
        table.add_column("Default", style="green")
        table.add_column("Description & Options", style="white")

        if isinstance(schema_or_dict, type) and issubclass(schema_or_dict, BaseModel):
            for f_name, f_info in schema_or_dict.model_fields.items():
                type_str = _format_type_name(f_info.annotation)
                default_str = str(f_info.default) if f_info.default is not None else "[dim]none[/dim]"
                desc_str = f_info.description or ""
                table.add_row(f_name, type_str, default_str, desc_str)
        elif isinstance(schema_or_dict, dict):
            for f_name, info in sorted(schema_or_dict.items()):
                if isinstance(info, dict):
                    default_obj = info.get("default")
                    fallback_type = type(default_obj).__name__ if default_obj is not None else "str"
                    type_str = str(info.get("type", fallback_type))
                    default_str = str(default_obj) if default_obj is not None else "[dim]none[/dim]"
                    desc_str = str(info.get("description", ""))
                    if "choices" in info and isinstance(info["choices"], (list, tuple)):
                        choices_str = ", ".join(f"[cyan]{c}[/cyan]" for c in info["choices"])
                        opt_note = f"[dim]options:[/dim] {choices_str}"
                        desc_block = f"{desc_str}\n{opt_note}" if desc_str else opt_note
                    else:
                        desc_block = desc_str
                    table.add_row(f_name, type_str, default_str, desc_block)
                else:
                    table.add_row(f_name, type(info).__name__, str(info), "")

        console.print(table)


def _handle_settings_init() -> None:
    template = skein.generate_settings_template()
    skein._settings_file.parent.mkdir(parents=True, exist_ok=True)
    skein._settings_file.write_text(template, encoding="utf-8")
    console.print(
        f"  [bold green]✓[/bold green] Generated documented settings template at\n"
        f"    [bold white]{skein._settings_file}[/bold white]."
    )


@app.command("settings")
def cmd_settings(
    action: str | None = typer.Argument(None, help="Action: get, set, reset, init, docs"),
    yarn_name: str | None = typer.Argument(None, help="Target yarn name (e.g. weave, hyprland, web_research)"),
    key: str | None = typer.Argument(None, help="Setting key"),
    value: str | None = typer.Argument(None, help="Setting value"),
):
    """Inspect and manage per-yarn user configuration (~/.config/textile/settings.toml)."""
    ensure_initialized()

    if action == "init":
        _handle_settings_init()
    elif action == "docs":
        _render_schema_docs(yarn_name)
    elif action == "get" and yarn_name:
        settings = skein.get_yarn_settings(yarn_name)
        if key:
            console.print(f"[bold cyan]{yarn_name}.{key}:[/bold cyan] {settings.get(key)}")
        else:
            _render_yarn_settings_table(yarn_name, settings)
    elif action == "set" and yarn_name and key and value is not None:
        current = skein.get_yarn_settings(yarn_name)
        current[key] = _parse_cli_setting_val(value)
        skein.set_yarn_settings(yarn_name, current)
        console.print(f"  [bold green]✓[/bold green] Set [bold white]{yarn_name}.{key}[/bold white] = {current[key]}.")
    elif action == "reset" and yarn_name:
        skein.set_yarn_settings(yarn_name, {})
        console.print(f"  [bold yellow]✓[/bold yellow] Reset settings for yarn [bold white]{yarn_name}[/bold white].")
    else:
        _render_all_settings_table(skein.get_all_settings())



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
    report_dict = audit_all(loom, skein).model_dump()

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

    table = Table(
        box=box.ROUNDED,
        border_style="dim",
        header_style="bold bright_cyan",
        show_edge=True,
        padding=(0, 1),
    )
    table.add_column("Yarn", style="bold cyan")
    table.add_column("Layer", justify="center")
    table.add_column("Status", justify="center")
    table.add_column("Strands", justify="right")

    for p in audit_report.yarns:
        yarn_name = str(p.get("yarn_name") or p.get("name") or "")
        p_health = str(p.get("health_status") or p.get("health") or "healthy").upper()
        p_color = "green" if p_health == "HEALTHY" else ("yellow" if p_health == "DEGRADED" else "red")
        strands_list = p.get("strands_report") or []
        strands_count = (
            len(strands_list)
            if isinstance(strands_list, list) and strands_list
            else p.get("strands_count", 0)
        )
        table.add_row(
            yarn_name,
            str(p.get("layer", 10)),
            f"[{p_color}]{p_health}[/{p_color}]",
            str(strands_count),
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

    console.print(
        f"\n  [bold bright_cyan]Core Task Ledger[/bold bright_cyan] "
        f"[dim]• {len(active)} active tasks[/dim]\n"
    )
    table = Table(
        box=box.ROUNDED,
        border_style="dim",
        header_style="bold bright_cyan",
        show_edge=True,
        padding=(0, 1),
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


@app.command("yarn")
def cmd_yarn(
    action: str = typer.Argument("list", help="Action: list, install, remove, paths"),
    target: str | None = typer.Argument(None, help="Yarn name, git repository URL, or local path"),
):
    """Manage installed capability yarns, discovery search paths, and third-party extensions."""
    ensure_initialized()
    user_yarns = Path(platformdirs.user_data_dir("textile")) / "yarns"

    if action in ("paths", "search-paths"):
        console.print("\n  [bold cyan]Textile Yarn Discovery Search Paths (in priority order):[/bold cyan]\n")
        for i, p in enumerate(skein.get_search_paths(), 1):
            exists_str = "[green]exists[/green]" if p.exists() else "[dim]not found[/dim]"
            console.print(f"  [bold yellow]{i}.[/bold yellow] {p} ({exists_str})")
        console.print()
        return

    if action == "install" and target:
        user_yarns.mkdir(parents=True, exist_ok=True)
        target_path = Path(target).expanduser().resolve()
        if target_path.exists() and target_path.is_dir():
            dest = user_yarns / target_path.name
            shutil.copytree(target_path, dest, dirs_exist_ok=True)
            console.print(f"  [bold green]✓[/bold green] Installed yarn from [bold white]{target}[/bold white]")
            console.print(f"    Destination: {dest}")
        else:
            repo_url = (
                target
                if target.startswith(("http://", "https://", "git@"))
                else f"https://github.com/{target}.git"
            )
            raw_name = target.rstrip("/").split("/")[-1].replace(".git", "")
            repo_name = raw_name.replace("textile-yarn-", "").replace("textile-", "")
            dest = user_yarns / repo_name
            git_bin = shutil.which("git")
            if not git_bin:
                console.print("  [bold red]Error:[/bold red] git binary not found in PATH.")
                return
            res = subprocess.run(
                [git_bin, "clone", "--depth", "1", repo_url, str(dest)],
                capture_output=True,
                text=True,
                check=False,
            )
            if res.returncode != 0:
                console.print(f"  [bold red]Error installing yarn:[/bold red] {res.stderr.strip()}")
                return
            console.print(
                f"  [bold green]✓[/bold green] Installed yarn [bold white]{repo_name}[/bold white] from {repo_url}"
            )
            console.print(f"    Destination: {dest}")

        skein._initialized = False
        ensure_initialized()
        return

    if action == "remove" and target:
        dest = user_yarns / target
        if dest.exists():
            shutil.rmtree(dest)
            console.print(
                f"  [bold yellow]✓[/bold yellow] Removed yarn [bold white]{target}[/bold white] from {dest}"
            )
        else:
            console.print(f"  [bold red]Error:[/bold red] Yarn '{target}' not found in {user_yarns}.")
        return

    # Default action: list
    console.print(
        f"\n  [bold bright_cyan]Discovered Capability Yarns[/bold bright_cyan] "
        f"[dim]• {len(skein.all_yarns)} active[/dim]\n"
    )
    table = Table(
        box=box.ROUNDED,
        border_style="dim",
        header_style="bold bright_cyan",
        show_edge=True,
        padding=(0, 1),
    )
    table.add_column("Yarn", style="bold cyan", width=18)
    table.add_column("Layer", style="bold yellow", width=8)
    table.add_column("Publisher", width=12)
    table.add_column("Strands", justify="right", width=8)
    table.add_column("Description", style="dim")

    for name, yarn in sorted(skein.all_yarns.items()):
        table.add_row(
            name,
            str(yarn.layer),
            yarn.publisher or "textile",
            str(len(yarn.get_strands())),
            yarn.description,
        )
    console.print(table)

