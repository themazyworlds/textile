"""
Textile Skein Coordinator Mixin & Signals.
Unifies yarn lifecycle management, settings schema configuration, and filesystem discovery.
"""

from pathlib import Path
from typing import Any

lazy import blinker

lazy from textile.core.bus import bus, request
lazy from textile.core.skein.discovery import (
    find_yarn_files,
    get_yarn_search_paths,
    parse_yarn_manifest_ast,
    probe_isolated_yarn,
    read_probe_cache,
    read_strand_index,
)
lazy from textile.core.skein.mesh import skein


class SkeinMixin:
    """Mixin providing plugin lifecycle, settings, and discovery methods for Camshaft."""

    class SkeinSignals:
        yarn_toggle_input: blinker.Signal = bus.signal("yarn:toggle_input")
        yarn_status_changed: blinker.Signal = bus.signal("yarn:status_changed")

    @staticmethod
    def toggle_yarn(yarn_name: str) -> bool:
        """Toggle a yarn's enabled state via input event."""
        return bool(request(SkeinMixin.SkeinSignals.yarn_toggle_input, yarn_name=yarn_name))

    @staticmethod
    def get_active_yarns() -> dict[str, Any]:
        """Retrieve all currently active/enabled yarns directly."""
        return skein.get_active_yarns()

    @staticmethod
    def get_all_yarns() -> dict[str, Any]:
        """Retrieve all discovered yarns directly."""
        return skein.get_all_yarns()

    @staticmethod
    def get_yarn(name: str) -> Any:
        """Resolve a specific yarn by name directly."""
        return skein.get_yarn(name)

    @staticmethod
    def register_yarn(yarn: Any) -> None:
        """Register a yarn instance directly into Skein."""
        skein.register_yarn(yarn)

    @staticmethod
    def is_yarn_enabled(yarn_name: str) -> bool:
        """Check whether a specific yarn is enabled directly."""
        return skein.is_enabled(yarn_name)

    @staticmethod
    def set_yarn_enabled(yarn_name: str, enabled: bool) -> None:
        """Enable or disable a yarn directly."""
        skein.set_yarn_enabled(yarn_name, enabled)
        bus.signal("yarn:status_changed").send("skein", yarn_name=yarn_name, enabled=enabled)

    @staticmethod
    def get_search_paths() -> list[Any]:
        """Retrieve yarn discovery search paths directly."""
        return skein.get_search_paths()

    @staticmethod
    def reload_plugins() -> None:
        """Reload all discovered plugins from disk directly."""
        skein.reload_plugins()

    @staticmethod
    def get_yarn_settings(yarn_name: str) -> dict[str, Any]:
        """Retrieve persisted settings overrides for a yarn directly."""
        return skein.get_yarn_settings(yarn_name)

    @staticmethod
    def set_yarn_settings(yarn_name: str, settings: dict[str, Any]) -> None:
        """Persist settings overrides for a yarn directly."""
        skein.set_yarn_settings(yarn_name, settings)

    @staticmethod
    def get_all_settings() -> dict[str, Any]:
        """Retrieve all settings overrides directly."""
        return skein.get_all_settings()

    @staticmethod
    def get_all_yarn_schemas() -> dict[str, Any]:
        """Retrieve all yarn configuration schemas directly."""
        return skein.get_all_yarn_schemas()

    @staticmethod
    def generate_settings_template() -> str:
        """Generate documented settings TOML template directly."""
        return skein.generate_settings_template()

    @property
    def settings_file(self) -> Path:
        """Resolve path to user settings.toml directly."""
        return skein._settings_file

    @staticmethod
    def get_yarn_search_paths(*, config_dir: Path | None = None) -> list[Path]:
        """Retrieve discovery search paths directly."""
        return get_yarn_search_paths(config_dir=config_dir)

    @staticmethod
    def read_strand_index() -> dict[str, Any]:
        """Read compiled strand index directly."""
        return read_strand_index()

    @staticmethod
    def read_probe_cache() -> dict[str, Any]:
        """Read isolated AST probe cache directly."""
        return read_probe_cache()

    @staticmethod
    def probe_isolated_yarn(file_path: Path) -> Any:
        """Probe an isolated yarn module directly."""
        return probe_isolated_yarn(file_path)

    @staticmethod
    def find_yarn_files(target_dir: Path) -> list[Path]:
        """Discover Python yarn entry points in target directory."""
        return find_yarn_files(target_dir)

    @staticmethod
    def parse_yarn_manifest_ast(file_path: Path) -> dict[str, Any] | None:
        """Parse yarn AST manifest directly."""
        return parse_yarn_manifest_ast(file_path)


__all__ = ["SkeinMixin"]
