"""
Textile Core Settings Subsystem & Auto-Documented Configuration Generator.
Powered by Pydantic v2 and pydantic-settings.
"""

import os
import tomllib
from pathlib import Path
from typing import Any, get_args, get_origin

from pydantic import BaseModel
from pydantic_core import PydanticUndefined
from pydantic_settings import BaseSettings, SettingsConfigDict


class YarnSettings(BaseSettings):
    """Base class for all Textile Capability Yarn settings schemas."""

    model_config = SettingsConfigDict(
        extra="ignore",
        case_sensitive=False,
        arbitrary_types_allowed=True,
    )


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
    except (OSError, tomllib.TOMLDecodeError):
        return {}


def _format_type_name(annotation: Any) -> str:
    """Format Python type annotations into human-friendly strings."""
    if annotation is None or annotation is type(None):
        return "none"

    origin = get_origin(annotation)
    args = get_args(annotation)

    if origin is None:
        if isinstance(annotation, type):
            return annotation.__name__
        return str(annotation)

    origin_name = getattr(origin, "__name__", str(origin)).lower()
    if "union" in origin_name:
        non_none = [a for a in args if a is not type(None)]
        if len(non_none) == 1:
            return f"optional[{_format_type_name(non_none[0])}]"
        return " | ".join(_format_type_name(a) for a in args)

    if "literal" in origin_name:
        choices = ", ".join(f'"{a}"' if isinstance(a, str) else str(a) for a in args)
        return f"choice: [{choices}]"

    if args:
        arg_names = ", ".join(_format_type_name(a) for a in args)
        return f"{origin_name}[{arg_names}]"

    return origin_name


def _format_toml_literal(val: Any) -> str:
    """Format a Python default value into TOML literal syntax."""
    if val is None or val is PydanticUndefined:
        return '""'
    if isinstance(val, bool):
        return "true" if val else "false"
    if isinstance(val, (int, float)):
        return str(val)
    if isinstance(val, str):
        escaped = val.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
        return f'"{escaped}"'
    if isinstance(val, (list, tuple, set)):
        items = ", ".join(_format_toml_literal(x) for x in val)
        return f"[{items}]"
    if isinstance(val, dict):
        items = ", ".join(f"{k} = {_format_toml_literal(v)}" for k, v in val.items())
        return f"{{{items}}}"
    return f'"{val}"'


def _render_schema_section(
    sections: list[str],
    schema_cls: type[BaseModel],
    yarn_current: dict[str, Any],
) -> None:
    doc = (schema_cls.__doc__ or "").strip()
    if doc:
        sections.append(f"# {doc}")
    for f_name, f_info in schema_cls.model_fields.items():
        desc = f_info.description or ""
        type_str = _format_type_name(f_info.annotation)
        val = yarn_current.get(f_name, f_info.default)

        if desc:
            for desc_line in desc.splitlines():
                sections.append(f"# {desc_line}")
        sections.append(f"# type: {type_str}")

        if val is not None and val is not PydanticUndefined:
            sections.append(f"{f_name} = {_format_toml_literal(val)}")
        else:
            sections.append(f"# {f_name} = {_format_toml_literal(val)}")
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

