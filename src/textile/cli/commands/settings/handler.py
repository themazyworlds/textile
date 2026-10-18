"""
Settings Command Handler.
Manages user configuration (~/.config/textile/settings.toml) and documents yarn schemas.
"""

from typing import Any

lazy from pydantic import BaseModel

from textile.cli.ui import Column, console, print_table
lazy from textile.core.definitions.settings import _format_type_name
lazy from textile.core.orchestration.skein import skein


def parse_cli_setting_val(raw: str) -> Any:
    """Parse raw CLI string value to bool, int, float, or string."""
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


def render_yarn_settings_table(yarn_name: str, settings: dict[str, Any]) -> None:
    """Render table of configuration settings for a single yarn."""
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


def render_all_settings_table(all_settings: dict[str, Any]) -> None:
    """Render table of all user configuration overrides."""
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


def render_schema_docs(yarn_name: str | None = None) -> None:
    """Reflect and render schema documentation for yarn settings models."""
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


def handle_settings_init() -> None:
    """Generate documented default ~/.config/textile/settings.toml configuration file."""
    template = skein.generate_settings_template()
    skein._settings_file.parent.mkdir(parents=True, exist_ok=True)
    skein._settings_file.write_text(template, encoding="utf-8")
    console.print(
        f"  [bold green]✓[/bold green] Generated documented settings template at\n"
        f"    [bold white]{skein._settings_file}[/bold white]."
    )
