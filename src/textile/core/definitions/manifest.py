"""
Textile Core Yarn Manifest & Layer Metadata Definitions.
"""

import contextlib
import logging
import tomllib
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, ValidationError

logger = logging.getLogger(__name__)

# Standard Layer Tiers (Higher number = outer layer with higher override authority)
LAYER_BASE = 10  # Base OS / Pure POSIX kernel fallbacks
LAYER_DESKTOP_PROTOCOL = 50  # Generic Wayland, XDG, D-Bus protocols
LAYER_COMPOSITOR_DE = 100  # Specific Compositors & DEs (Hyprland, Caelestia, GNOME, KDE)
LAYER_SESSION_MANAGER = 150  # Session Managers & Cgroup Wrappers (UWSM, systemd-run)
LAYER_USER_OVERRIDE = 1000  # User custom overrides (~/.config/textile/yarns/)


class SettingFieldManifest(BaseModel):
    """Schema and default definition for a single configurable setting in a Yarn manifest."""

    type: str = "string"
    default: Any = None
    description: str = ""
    options: list[Any] | None = None


class YarnManifest(BaseModel):
    """Declarative static manifest for Textile Yarns parsed from pyproject.toml, yarn.toml, or <name>.toml."""

    name: str
    publisher: str = ""
    version: str = "1.0.0"
    manifest_version: int = 1
    layer: int = LAYER_DESKTOP_PROTOCOL
    description: str = ""
    entrypoint: str = ""
    dependencies: list[str] = Field(default_factory=list)
    resources: list[str] = Field(default_factory=list)
    settings: dict[str, SettingFieldManifest] = Field(default_factory=dict)

    @property
    def python_dependencies(self) -> list[str]:
        return self.dependencies

    @python_dependencies.setter
    def python_dependencies(self, value: list[str]) -> None:
        self.dependencies = value

    def get_default_settings(self) -> dict[str, Any]:
        """Extract declared default values dictionary from this manifest."""
        return {k: v.default for k, v in self.settings.items() if v.default is not None}

    def create_settings_model(self) -> type[BaseModel] | None:
        """Dynamically construct a Pydantic Settings model directly from this manifest's [settings] table."""
        if not self.settings:
            return None

        from typing import Literal  # noqa: PLC0415

        from pydantic import create_model  # noqa: PLC0415

        from textile.core.definitions.settings import YarnSettings  # noqa: PLC0415

        fields: dict[str, Any] = {}
        for name, field_spec in self.settings.items():
            if field_spec.options:
                ann = Literal[tuple(field_spec.options)]  # pyright: ignore[reportInvalidTypeForm]
            elif field_spec.type in ("integer", "int"):
                ann = int
            elif field_spec.type in ("float", "number"):
                ann = float
            elif field_spec.type in ("boolean", "bool"):
                ann = bool
            elif field_spec.type in ("list", "array"):
                ann = list[str]
            else:
                ann = str

            fields[name] = (
                ann,
                Field(
                    default=field_spec.default,
                    description=field_spec.description,
                ),
            )

        model_cls_name = f"{self.name.capitalize()}Settings"
        doc = f"User-adjustable settings for {self.name} capability yarn."
        return create_model(
            model_cls_name,
            __base__=YarnSettings,
            __doc__=doc,
            **fields,
        )

    @classmethod
    def from_toml(cls, path: Path) -> YarnManifest:
        with path.open("rb") as f:
            raw_data = tomllib.load(f)
        try:
            # 1. Check if loading from pyproject.toml [tool.textile.yarn] or [tool.textile]
            if path.name == "pyproject.toml" or "tool" in raw_data and "textile" in raw_data.get("tool", {}):
                tool_textile = raw_data.get("tool", {}).get("textile", {})
                yarn_data = tool_textile.get("yarn", tool_textile)
                proj = raw_data.get("project", {})
                name = yarn_data.get("name") or proj.get("name") or path.parent.name
                deps = yarn_data.get("dependencies") or proj.get("dependencies", [])
                desc = yarn_data.get("description") or proj.get("description", "")
                version = yarn_data.get("version") or proj.get("version", "1.0.0")
                data = {
                    **yarn_data,
                    "name": name,
                    "dependencies": deps if isinstance(deps, list) else [],
                    "description": desc,
                    "version": version,
                }
                return cls.model_validate(data)

            # 2. Standard yarn.toml or <name>.toml
            yarn_data = raw_data.get("yarn", raw_data)
            deps_raw = yarn_data.get("dependencies", raw_data.get("dependencies", []))
            if isinstance(deps_raw, dict):
                deps_list = deps_raw.get("python", [])
            elif isinstance(deps_raw, list):
                deps_list = deps_raw
            else:
                deps_list = []

            # If no dependencies declared in yarn.toml, check if sibling pyproject.toml declares them
            if not deps_list:
                sibling_pyproj = path.parent / "pyproject.toml"
                if sibling_pyproj.exists():
                    with contextlib.suppress(Exception), sibling_pyproj.open("rb") as pf:
                        p_data = tomllib.load(pf)
                        deps_list = p_data.get("project", {}).get("dependencies", [])

            res_data = yarn_data.get("resources", raw_data.get("resources", []))
            settings_data = raw_data.get("settings", {})
            name = yarn_data.get("name", path.parent.name)
            data = {
                **yarn_data,
                "name": name,
                "dependencies": deps_list if isinstance(deps_list, list) else [],
                "resources": res_data,
                "settings": settings_data,
            }
            return cls.model_validate(data)
        except ValidationError as e:
            err = e.errors()[0]
            loc = ".".join(str(x) for x in err["loc"]) if err["loc"] else "field"
            msg = f"Validation Hint: Manifest '{path.name}' field '{loc}' failed validation: {err['msg']}."
            logger.warning(msg)
            raise ValueError(msg) from e

