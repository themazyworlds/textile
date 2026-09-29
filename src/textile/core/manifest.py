"""
Textile Core Yarn Manifest & Layer Metadata Definitions.
"""

import logging
import tomllib
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError

logger = logging.getLogger(__name__)

# Standard Layer Tiers (Higher number = outer layer with higher override authority)
LAYER_BASE = 10  # Base OS / Pure POSIX kernel fallbacks
LAYER_DESKTOP_PROTOCOL = 50  # Generic Wayland, XDG, D-Bus protocols
LAYER_COMPOSITOR_DE = 100  # Specific Compositors & DEs (Hyprland, Caelestia, GNOME, KDE)
LAYER_SESSION_MANAGER = 150  # Session Managers & Cgroup Wrappers (UWSM, systemd-run)
LAYER_USER_OVERRIDE = 1000  # User custom overrides (~/.config/textile/yarns/)


class DependenciesManifest(BaseModel):
    """Declared python and system CLI package requirements."""

    python: list[str] = Field(default_factory=list)
    system: list[str] = Field(default_factory=list)


class YarnManifest(BaseModel):
    """Declarative static manifest for Textile Yarns parsed from yarn.toml or <name>.toml."""

    name: str
    publisher: str = ""
    version: str = "1.0.0"
    manifest_version: int = 1
    layer: int = LAYER_DESKTOP_PROTOCOL
    description: str = ""
    dependencies: DependenciesManifest = Field(default_factory=DependenciesManifest)
    resources: list[str] = Field(default_factory=list)

    @property
    def python_dependencies(self) -> list[str]:
        return self.dependencies.python

    @python_dependencies.setter
    def python_dependencies(self, value: list[str]) -> None:
        self.dependencies.python = value

    @property
    def system_dependencies(self) -> list[str]:
        return self.dependencies.system

    @classmethod
    def from_toml(cls, path: Path) -> "YarnManifest":
        with open(path, "rb") as f:
            raw_data = tomllib.load(f)
        try:
            yarn_data = raw_data.get("yarn", {})
            deps_data = raw_data.get("dependencies", {})
            res_data = raw_data.get("yarn", {}).get("resources", raw_data.get("resources", []))
            data = {
                **yarn_data,
                "dependencies": deps_data,
                "resources": res_data,
            }
            return cls.model_validate(data)
        except ValidationError as e:
            err = e.errors()[0]
            loc = ".".join(str(x) for x in err["loc"]) if err["loc"] else "field"
            msg = f"Validation Hint: Manifest '{path.name}' field '{loc}' failed validation: {err['msg']}."
            logger.warning(msg)
            raise ValueError(msg) from e
