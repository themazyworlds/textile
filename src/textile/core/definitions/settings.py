"""
Textile Core Settings Subsystem & Auto-Documented Configuration Generator.
Powered by Pydantic v2 and pydantic-settings.
"""

import tomllib
from pathlib import Path
from typing import Any, get_args, get_origin

import platformdirs
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


def get_user_yarn_settings(yarn_name: str) -> dict[str, Any]:
    """Retrieve raw user settings dictionary for a specific yarn from ~/.config/textile/settings.toml."""
    settings_file = Path(platformdirs.user_config_dir("textile")) / "settings.toml"
    if not settings_file.exists():
        return {}
    try:
        with settings_file.open("rb") as f:
            data = tomllib.load(f)
            return data.get(yarn_name, {})
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


def generate_documented_toml(
    yarn_schemas: dict[str, type[BaseModel]],
    current_settings: dict[str, dict[str, Any]] | None = None,
) -> str:
    """Generate a fully self-documented ~/.config/textile/settings.toml template from Pydantic schemas."""
    sections: list[str] = [
        "# =============================================================================",
        "# Textile Desktop Intelligence Fabric — User Configuration",
        "# Location: ~/.config/textile/settings.toml",
        "# Generated automatically from Yarn Manifests and Pydantic Schemas.",
        "# =============================================================================",
        "",
    ]
    current = current_settings or {}

    for yarn_name, schema_cls in sorted(yarn_schemas.items()):
        doc = (schema_cls.__doc__ or "").strip()
        sections.append(f"[{yarn_name}]")
        if doc:
            sections.append(f"# {doc}")

        yarn_current = current.get(yarn_name, {})

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

    return "\n".join(sections).strip() + "\n"

