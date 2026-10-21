"""
Textile Core Settings Subsystem & Auto-Documented Configuration Generator.
Powered by Pydantic v2 and pydantic-settings.
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any, cast, get_args, get_origin

lazy from pydantic import BaseModel
lazy from pydantic_core import PydanticUndefined
lazy from pydantic_settings import BaseSettings, SettingsConfigDict


def __getattr__(name: str) -> Any:
    if name == "YarnSettings":

        class YarnSettings(BaseSettings):
            """Base class for all Textile Capability Yarn settings schemas."""

            model_config = SettingsConfigDict(
                extra="ignore",
                case_sensitive=False,
                arbitrary_types_allowed=True,
            )

        globals()["YarnSettings"] = YarnSettings
        return YarnSettings
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def get_settings_file_path() -> Path:
    """Return the active settings.toml path respecting TEXTILE_CONFIG_DIR environment override."""
    config_dir = os.environ.get("TEXTILE_CONFIG_DIR")
    if config_dir:
        return Path(config_dir) / "settings.toml"
    return Path.home() / ".config" / "textile" / "settings.toml"


def get_user_yarn_settings(yarn_name: str, settings_file: Path | None = None) -> dict[str, Any]:
    """Retrieve raw user settings dictionary for a specific yarn from settings.toml."""
    target_file = settings_file or get_settings_file_path()
    if not target_file.exists():
        return {}
    try:
        with target_file.open("rb") as f:
            data = tomllib.load(f)
            if isinstance(data, dict):
                yarn_data = data.get(yarn_name, {})
                return dict(yarn_data) if isinstance(yarn_data, dict) else {}
            return {}
    except OSError, tomllib.TOMLDecodeError:
        return {}


def _format_type_name(annotation: Any) -> str:
    """Format Python type annotations into human-friendly strings."""
    if annotation is None or annotation is type(None):
        return "none"

    origin = get_origin(annotation)
    args = get_args(annotation)

    if origin is None:
        return annotation.__name__ if isinstance(annotation, type) else str(annotation)

    origin_name = getattr(origin, "__name__", str(origin)).lower()
    if "union" in origin_name:
        non_none = [a for a in args if a is not type(None)]
        return (
            f"optional[{_format_type_name(non_none[0])}]"
            if len(non_none) == 1
            else " | ".join(_format_type_name(a) for a in args)
        )

    if "literal" in origin_name:
        choices = ", ".join(f'"{a}"' if isinstance(a, str) else str(a) for a in args)
        return f"choice: [{choices}]"

    if args:
        arg_names = ", ".join(_format_type_name(a) for a in args)
        return f"{origin_name}[{arg_names}]"

    return origin_name


def _format_toml_literal(val: Any) -> str:
    if val is None:
        return '""'
    if isinstance(val, bool):
        return "true" if val else "false"
    if isinstance(val, (int, float)):
        return str(val)
    if isinstance(val, list):
        items = [_format_toml_literal(v) for v in val]
        return f"[{', '.join(items)}]"
    s = str(val).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{s}"'


def _render_schema_section(
    sections: list[str],
    schema: type[BaseModel],
    yarn_current: dict[str, Any],
) -> None:
    for f_name, f_info in sorted(schema.model_fields.items()):
        type_str = _format_type_name(f_info.annotation)
        val = yarn_current.get(f_name)
        if val is None:
            val = cast(Any, f_info.default_factory)() if f_info.default_factory is not None else f_info.default
            if val is PydanticUndefined:
                val = ""

        if f_info.description:
            for desc_line in f_info.description.splitlines():
                sections.append(f"# {desc_line}")
        sections.append(f"# type: {type_str}")
        sections.append(f"{f_name} = {_format_toml_literal(val)}")
        sections.append("")


def _render_dict_section(
    sections: list[str],
    settings_dict: dict[str, Any],
    yarn_current: dict[str, Any],
) -> None:
    for f_name, item_or_val in sorted(settings_dict.items()):
        if isinstance(item_or_val, dict):
            desc = item_or_val.get("description", "")
            choices = item_or_val.get("choices")
            default_val = item_or_val.get("default")
            val = yarn_current.get(f_name, default_val)
            fallback_type = type(default_val).__name__ if default_val is not None else "str"
            type_str = item_or_val.get("type", fallback_type)

            if desc:
                for desc_line in str(desc).splitlines():
                    sections.append(f"# {desc_line}")
            if choices and isinstance(choices, (list, tuple)):
                choices_str = ", ".join(f'"{c}"' if isinstance(c, str) else str(c) for c in choices)
                sections.append(f"# choices: [{choices_str}]")
            sections.append(f"# type: {type_str}")
            sections.append(f"{f_name} = {_format_toml_literal(val)}")
            sections.append("")
        else:
            val = yarn_current.get(f_name, item_or_val)
            type_str = type(item_or_val).__name__ if item_or_val is not None else "str"
            sections.append(f"# type: {type_str}")
            sections.append(f"{f_name} = {_format_toml_literal(val)}")
            sections.append("")


def generate_documented_toml(
    yarn_schemas: dict[str, Any],
    current_settings: dict[str, dict[str, Any]] | None = None,
) -> str:
    """Generate a fully self-documented ~/.config/textile/settings.toml template from schemas and pyproject defaults."""
    sections: list[str] = [
        "# Textile settings",
        "# Edit any setting below to customize per-yarn configuration.",
        "",
    ]
    current = current_settings or {}

    for yarn_name, schema_or_dict in sorted(yarn_schemas.items()):
        sections.append(f"[{yarn_name}]")
        yarn_current = current.get(yarn_name, {})

        if isinstance(schema_or_dict, type) and issubclass(schema_or_dict, BaseModel):
            _render_schema_section(sections, schema_or_dict, yarn_current)
        elif isinstance(schema_or_dict, dict):
            _render_dict_section(sections, schema_or_dict, yarn_current)

    return "\n".join(sections).strip() + "\n"


def dumps_toml(data: dict[str, Any]) -> str:
    """Format an arbitrary settings dictionary into valid TOML format."""
    lines: list[str] = [
        "# Textile settings",
        "# Edit any setting below to customize per-yarn configuration.",
        "",
    ]
    top_level = [f"{k} = {_format_toml_literal(v)}" for k, v in data.items() if not isinstance(v, dict)]
    if top_level:
        lines.extend(top_level)
        lines.append("")

    for section, table in data.items():
        if isinstance(table, dict):
            lines.append(f"[{section}]")
            for k, v in table.items():
                lines.append(f"{k} = {_format_toml_literal(v)}")
            lines.append("")

    return "\n".join(lines).strip() + "\n"


_dumps_toml = dumps_toml
_generate_documented_toml = generate_documented_toml

__all__ = [
    "dumps_toml",
    "generate_documented_toml",
    "get_settings_file_path",
    "get_user_yarn_settings",
]
