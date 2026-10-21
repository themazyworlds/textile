"""
Settings Command Definition (`quill settings`).
"""

import typer

from textile.cli.quill import quill
lazy from textile.cli.commands.settings.handler import (
    handle_settings_init,
    parse_cli_setting_val,
    render_all_settings_table,
    render_schema_docs,
    render_yarn_settings_table,
)
lazy from textile.cli.ui import console
lazy from textile.core.camshaft import camshaft


@quill.command("settings")
def cmd_settings(
    action: str | None = typer.Argument(None, help="get, set, reset, init, docs"),
    yarn_name: str | None = typer.Argument(None, help="Target yarn name"),
    key: str | None = typer.Argument(None, help="Setting key"),
    value: str | None = typer.Argument(None, help="Setting value"),
):
    """Inspect and manage per-yarn user configuration (~/.config/textile/settings.toml)."""
    camshaft.initialize()

    if action == "init":
        handle_settings_init()
    elif action == "docs":
        render_schema_docs(yarn_name)
    elif action == "get" and yarn_name:
        settings = camshaft.get_yarn_settings(yarn_name)
        if key:
            console.print(f"[bold cyan]{yarn_name}.{key}:[/bold cyan] {settings.get(key)}")
        else:
            render_yarn_settings_table(yarn_name, settings)
    elif action == "set" and yarn_name and key and value is not None:
        current = camshaft.get_yarn_settings(yarn_name)
        current[key] = parse_cli_setting_val(value)
        camshaft.set_yarn_settings(yarn_name, current)
        console.print(f"  [bold green]✓[/bold green] Set [bold white]{yarn_name}.{key}[/bold white] = {current[key]}.")
    elif action == "reset" and yarn_name:
        camshaft.set_yarn_settings(yarn_name, {})
        console.print(f"  [bold yellow]✓[/bold yellow] Reset settings for yarn [bold white]{yarn_name}[/bold white].")
    else:
        render_all_settings_table(camshaft.get_all_settings())
