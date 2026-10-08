import contextlib
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import typer

from textile.core.cli.app import app, console
from textile.core.orchestration.loom import loom
from textile.core.orchestration.skein import skein
from textile.core.orchestration.twill import run_twill


@app.command("twill")
def cmd_twill():
    """Launch official Twill / MCP stdio server."""
    run_twill()


def _resolve_yarn_venv(agent_dir: Path) -> Path | None:
    """Locate the nearest or dedicated virtualenv for a yarn agent."""
    curr: Path | None = agent_dir
    while curr and curr != curr.parent:
        candidate = curr / ".venv"
        if candidate.is_dir():
            return candidate
        curr = curr.parent
    return None


@app.command("weave")
def cmd_weave(
    dev: bool = typer.Option(False, "--dev", help="Dev mode: auto-reload on file changes (lk agent dev)"),
    text: bool = typer.Option(False, "--text", help="Text-only mode, no mic/speaker (lk agent console --text)"),
):
    """Launch Weave real-time voice & desktop companion."""
    for search_path in skein.get_search_paths():
        agent_file = search_path / "weave" / "agent.py"
        if agent_file.exists():
            lk_bin = shutil.which("lk")
            if not lk_bin:
                console.print(
                    "  [bold red]Error:[/bold red] LiveKit CLI ('lk') not found on PATH.\n"
                    "  Install: curl -sSL https://get.livekit.io/cli | bash && lk cloud auth"
                )
                return

            cmd = [lk_bin, "agent", "dev" if dev else "console"]
            if not dev and text:
                cmd.append("--text")
            cmd.append("agent.py")

            env = dict(os.environ)
            yarn_venv = _resolve_yarn_venv(agent_file.parent)
            if yarn_venv:
                env["VIRTUAL_ENV"] = str(yarn_venv)
                env["PATH"] = f"{yarn_venv / 'bin'}:{env.get('PATH', '')}"
            else:
                env.pop("VIRTUAL_ENV", None)

            with contextlib.suppress(KeyboardInterrupt):
                subprocess.run(cmd, cwd=str(agent_file.parent), env=env, check=False)
            return

    console.print("  [bold red]Error:[/bold red] Weave voice companion is not installed or available.")


@app.command("canvas")
def cmd_canvas(
    action: str = typer.Argument("status", help="Canvas action: launch, close, mood, expression, talk, listen, status"),
    target: str | None = typer.Argument(None, help="Mood name, expression name, or on/off flag"),
):
    """Control the Quickshell Canvas Face UI and dynamic mood engine."""
    loom.initialize()
    canvas_yarn: Any = loom.active_yarns.get("canvas")
    if not canvas_yarn:
        console.print("  [bold red]Error:[/bold red] Canvas yarn is not installed or available.")
        return

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
