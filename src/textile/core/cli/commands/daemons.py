"""
Textile CLI Subsystem Daemon Commands (Twill MCP, Weave Voice AI, Canvas UI).
"""

import importlib

import typer

from textile.core.cli.app import app, console
from textile.core.twill import run_twill


@app.command("twill")
def cmd_twill():
    """Launch official Twill / MCP stdio server."""
    run_twill()


@app.command("weave")
def cmd_weave(
    dev: bool = typer.Option(False, "--dev", help="Run in dev LiveKit worker mode"),
    start_worker: bool = typer.Option(False, "--start-worker", help="Start background worker process"),
    text_mode: bool = typer.Option(False, "--text", help="Run in text-only console mode"),
):
    """Launch Weave real-time voice & desktop companion."""
    mod = importlib.import_module("textile.yarns.weave.weave")
    run_voice_agent = getattr(mod, "run_voice_agent")
    mode = "dev" if dev else ("start" if start_worker else "console")
    run_voice_agent(mode=mode, text_mode=text_mode)


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
