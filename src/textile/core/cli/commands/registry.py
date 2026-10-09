"""
Textile CLI Registry, Health Audit, and Blackboard Diagnostics Commands.
"""

import contextlib
import inspect
import shutil
import subprocess
from pathlib import Path
from typing import Any

import platformdirs
import typer
from pydantic import BaseModel
from rich.tree import Tree

from textile.core.cli.app import (
    TapestryStateModel,
    app,
    console,
    ensure_initialized,
)
from textile.core.cli.ui import Column, print_table
from textile.core.definitions.settings import _format_type_name
from textile.core.orchestration.loom import loom
from textile.core.orchestration.skein import skein
from textile.core.telemetry.blackboard import sensory_tapestry
from textile.core.telemetry.ledger import core_tapestry


@app.command("skein")
def cmd_skein(
    action: str | None = typer.Argument(None, help="enable, disable, toggle, tree"),
    yarn_target: str | None = typer.Argument(None, help="Target yarn name for enable/disable/toggle"),
):
    """Inspect and manage the Skein runtime layer hierarchy, policy engine, and yarn activation."""
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
    elif action == "tree":
        layers_map: dict[int, list[tuple[str, bool, int]]] = {}
        for name, yarn in skein.all_yarns.items():
            is_en = skein.is_enabled(name)
            strands_count = len(yarn.get_strands())
            layers_map.setdefault(yarn.layer, []).append((name, is_en, strands_count))

        tree = Tree(
            "[bold bright_cyan]Skein Runtime Hierarchy[/bold bright_cyan]",
            guide_style="dim cyan",
        )
        for layer_num in sorted(layers_map.keys(), reverse=True):
            layer_branch = tree.add(f"[bold magenta]Layer {layer_num}[/bold magenta]")
            for y_name, is_en, s_count in sorted(layers_map[layer_num], key=lambda x: x[0]):
                status_str = "[bold green]ACTIVE[/bold green]" if is_en else "[bold red]DISABLED[/bold red]"
                layer_branch.add(
                    f"[bold white]{y_name}[/bold white] "
                    f"[{status_str}] "
                    f"[dim]({s_count} strands)[/dim]"
                )
        console.print(tree)
        return

    rows = []
    for name, yarn in sorted(skein.all_yarns.items(), key=lambda x: (-x[1].layer, x[1].name)):
        is_en = skein.is_enabled(name)
        en_str = "[green]YES[/green]" if is_en else "[red]NO[/red]"
        desc = (yarn.description or "").splitlines()[0].strip() if yarn.description else ""
        strands_count = str(len(yarn.get_strands()))
        rows.append((yarn.name, str(yarn.layer), en_str, strands_count, desc))

    print_table(
        header_title="Skein",
        columns=[
            Column("Yarn", style="bold cyan", no_wrap=True),
            Column("Layer", style="dim", justify="center", no_wrap=True),
            Column("Enabled", justify="center", no_wrap=True),
            Column("Strands", justify="right", no_wrap=True),
            Column("Description", style="dim"),
        ],
        rows=rows,
    )


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
    rows = [(k, str(v)) for k, v in sorted(settings.items())]
    print_table(
        header_title="Settings",
        subtitle=yarn_name,
        columns=[
            Column("Setting Key", style="bold cyan"),
            Column("Value", style="green"),
        ],
        rows=rows,
    )


def _render_all_settings_table(all_settings: dict[str, Any]) -> None:
    if not all_settings:
        console.print("\n  [dim]No user overrides found in ~/.config/textile/settings.toml.[/dim]\n")
        return

    rows = []
    for y_name, s_dict in sorted(all_settings.items()):
        if isinstance(s_dict, dict):
            for k, v in sorted(s_dict.items()):
                rows.append((y_name, k, str(v)))

    print_table(
        header_title="Settings",
        columns=[
            Column("Yarn", style="bold cyan"),
            Column("Key", style="bold white"),
            Column("Value", style="green"),
        ],
        rows=rows,
    )


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
        rows = []
        if isinstance(schema_or_dict, type) and issubclass(schema_or_dict, BaseModel):
            for f_name, f_info in schema_or_dict.model_fields.items():
                type_str = _format_type_name(f_info.annotation)
                default_str = str(f_info.default) if f_info.default is not None else "[dim]none[/dim]"
                desc_str = f_info.description or ""
                rows.append((f_name, type_str, default_str, desc_str))
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
                    rows.append((f_name, type_str, default_str, desc_block))
                else:
                    rows.append((f_name, type(info).__name__, str(info), ""))

        print_table(
            header_title="Settings Schema",
            subtitle=y_name,
            columns=[
                Column("Setting", style="bold cyan"),
                Column("Type", style="dim", justify="center"),
                Column("Default", style="green"),
                Column("Description & Options", style="white"),
            ],
            rows=rows,
        )


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
    action: str | None = typer.Argument(None, help="get, set, reset, init, docs"),
    yarn_name: str | None = typer.Argument(None, help="Target yarn name"),
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

    rows = []
    for t in active:
        rows.append((t["task_id"][:8], t["strand_name"], str(t.get("tier", "-")), "[bold green]RUNNING[/bold green]"))
    for t in reversed(history):
        status_str = "[green]SUCCESS[/green]" if t.get("success") else "[red]FAILED[/red]"
        rows.append((t["task_id"][:8], t["strand_name"], str(t.get("tier", "-")), status_str))

    print_table(
        header_title="Tapestry",
        subtitle=f"{len(active)} active tasks",
        columns=[
            Column("Task ID", style="bold yellow", width=10),
            Column("Strand", style="bold white", width=28),
            Column("Tier", width=12),
            Column("Status", width=12),
        ],
        rows=rows,
    )


def _handle_yarn_paths() -> None:
    console.print("\n  [bold cyan]Textile Yarn Discovery Search Paths (in priority order):[/bold cyan]\n")
    for i, p in enumerate(skein.get_search_paths(), 1):
        exists_str = "[green]exists[/green]" if p.exists() else "[dim]not found[/dim]"
        console.print(f"  [bold yellow]{i}.[/bold yellow] {p} ({exists_str})")
    console.print()


def _handle_yarn_info(target: str) -> None:
    yarn = skein.all_yarns.get(target)
    if not yarn:
        console.print(f"  [bold red]Error:[/bold red] Yarn '[bold white]{target}[/bold white]' is not installed.")
        return

    source_path = "built-in / dynamic"
    with contextlib.suppress(TypeError, OSError):
        source_path = str(inspect.getfile(yarn.__class__))

    strands = yarn.get_strands()
    desc = (yarn.description or "").strip()
    deps = ", ".join(yarn.get_dependencies()) if yarn.get_dependencies() else "[dim]none[/dim]"

    console.print(f"\n  [bold bright_cyan]Yarn Info:[/bold bright_cyan] [bold white]{yarn.name}[/bold white]\n")
    console.print(f"  [bold cyan]Class:[/bold cyan]        {yarn.__class__.__name__}")
    console.print(f"  [bold cyan]Layer:[/bold cyan]        {yarn.layer}")
    console.print(f"  [bold cyan]Version:[/bold cyan]      {yarn.version}")
    console.print(f"  [bold cyan]Tailor:[/bold cyan]       {yarn.tailor}")
    console.print(f"  [bold cyan]Source:[/bold cyan]       {source_path}")
    console.print(f"  [bold cyan]Dependencies:[/bold cyan] {deps}")
    console.print(f"  [bold cyan]Description:[/bold cyan]  {desc}\n")

    if strands:
        rows = []
        for s in sorted(strands, key=lambda x: x.name):
            s_desc = (s.description or "").splitlines()[0].strip() if s.description else ""
            rows.append((s.name, s.tier, s_desc))
        print_table(
            header_title="Strands",
            subtitle=f"{len(strands)} registered",
            columns=[
                Column("Strand", style="bold cyan"),
                Column("Tier", justify="center", style="yellow"),
                Column("Description", style="dim"),
            ],
            rows=rows,
        )


def _handle_yarn_install(target: str, user_yarns: Path) -> None:
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


def _handle_yarn_remove(target: str, user_yarns: Path) -> None:
    dest = user_yarns / target
    if dest.exists():
        shutil.rmtree(dest)
        console.print(
            f"  [bold yellow]✓[/bold yellow] Removed yarn [bold white]{target}[/bold white] from {dest}"
        )
    else:
        console.print(f"  [bold red]Error:[/bold red] Yarn '{target}' not found in {user_yarns}.")


def _render_yarns_list_table() -> None:
    rows = []
    for name, yarn in sorted(skein.all_yarns.items()):
        desc = (yarn.description or "").splitlines()[0].strip() if yarn.description else ""
        rows.append((
            name,
            str(yarn.layer),
            yarn.tailor or "textile",
            yarn.version,
            str(len(yarn.get_strands())),
            desc,
        ))

    print_table(
        header_title="Installed Yarns",
        columns=[
            Column("Yarn", style="bold cyan", no_wrap=True),
            Column("Layer", style="dim", justify="center", no_wrap=True),
            Column("Tailor", no_wrap=True),
            Column("Version", style="green", no_wrap=True),
            Column("Strands", justify="right", no_wrap=True),
            Column("Description", style="dim"),
        ],
        rows=rows,
    )


@app.command("yarns")
def cmd_yarns(
    action: str = typer.Argument("list", help="list, info, install, remove, paths"),
    target: str | None = typer.Argument(None, help="Yarn name, git repository URL, or local path"),
):
    """Manage installed capability yarns, inspection, and discovery search paths."""
    ensure_initialized()
    user_yarns = Path(platformdirs.user_data_dir("textile")) / "yarns"

    if action in ("paths", "search-paths"):
        _handle_yarn_paths()
    elif action == "info" and target:
        _handle_yarn_info(target)
    elif action == "install" and target:
        _handle_yarn_install(target, user_yarns)
    elif action == "remove" and target:
        _handle_yarn_remove(target, user_yarns)
    else:
        _render_yarns_list_table()

