"""
Textile Skein - Layer 3 Symbolic Intent Compiler, Policy Engine, and Yarn Registry.
"""

import contextlib
import importlib
import importlib.util
import inspect
import os
import sys
import threading
import tomllib
from pathlib import Path
from typing import Any

import orjson
import platformdirs

from textile.core.definitions.errors import SAFE_EXCEPTIONS
from textile.core.definitions.settings import generate_documented_toml
from textile.core.execution.strands import Strand
from textile.core.execution.yarn import Yarn
from textile.core.security.context import PolicyViolationError
from textile.core.telemetry.log import get_logger

logger = get_logger(__name__)

__all__ = ["PolicyViolationError", "Skein", "skein"]


def _format_toml_val(val: Any) -> str:
    if isinstance(val, bool):
        return "true" if val else "false"
    if isinstance(val, (int, float)):
        return str(val)
    if isinstance(val, str):
        escaped = val.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
        return f'"{escaped}"'
    if isinstance(val, (list, tuple, set)):
        items = ", ".join(_format_toml_val(x) for x in val)
        return f"[{items}]"
    if isinstance(val, dict):
        items = ", ".join(f"{k} = {_format_toml_val(v)}" for k, v in val.items())
        return f"{{{items}}}"
    return f'"{str(val)}"'


def _dumps_toml(data: dict[str, Any]) -> str:
    lines: list[str] = [
        "# Textile settings",
        "# Edit any setting below to customize per-yarn configuration.",
        "",
    ]
    top_level = [f"{k} = {_format_toml_val(v)}" for k, v in data.items() if not isinstance(v, dict)]
    if top_level:
        lines.extend(top_level)
        lines.append("")

    # 2. Table sections
    for section, table in data.items():
        if isinstance(table, dict):
            lines.append(f"[{section}]")
            for k, v in table.items():
                lines.append(f"{k} = {_format_toml_val(v)}")
            lines.append("")

    return "\n".join(lines).strip() + "\n"


def get_yarn_search_paths(config_dir: Path | None = None) -> list[Path]:
    """Retrieve ordered list of filesystem search paths for yarn discovery using platformdirs."""
    paths: list[Path] = []

    # 1. Explicit environment variable override
    env_paths = os.environ.get("TEXTILE_YARN_PATH")
    if env_paths:
        for p in env_paths.split(":"):
            if p.strip():
                paths.append(Path(p.strip()).expanduser().resolve())

    # 2. User custom / override directory (~/.config/textile/yarns)
    user_config = config_dir or (Path(platformdirs.user_config_dir("textile")) / "yarns")
    paths.append(user_config.expanduser().resolve())

    # 3. User installed plugins directory (~/.local/share/textile/yarns)
    user_data = Path(platformdirs.user_data_dir("textile")) / "yarns"
    paths.append(user_data.expanduser().resolve())

    # 4. System-wide installed directories (/usr/local/share/textile/yarns, /usr/share/textile/yarns)
    site_dirs = platformdirs.site_data_dir("textile", multipath=True)
    for site_dir in site_dirs.split(":"):
        if site_dir.strip():
            paths.append((Path(site_dir.strip()) / "yarns").resolve())

    # 5. Sibling textile-yarns repo or workspace dev directory (if running from git source tree)
    with contextlib.suppress(Exception):
        sibling_yarns = Path(__file__).resolve().parents[5] / "textile-yarns" / "yarns"
        if sibling_yarns.exists():
            paths.append(sibling_yarns.resolve())
        repo_yarns = Path(__file__).resolve().parents[4] / "yarns"
        if repo_yarns.exists():
            paths.append(repo_yarns.resolve())

    # Deduplicate while preserving priority order
    seen: set[Path] = set()
    unique_paths: list[Path] = []
    for path in paths:
        if path not in seen:
            seen.add(path)
            unique_paths.append(path)

    return unique_paths


class Skein:
    """Manages yarn discovery, intent compilation, policy verification, and runtime health."""

    def __init__(self, config_dir: Path | None = None):
        self._lock = threading.RLock()
        self._config_dir = config_dir or (Path.home() / ".config" / "textile")
        self._config_file = self._config_dir / "yarns.json"
        self._settings_file = self._config_dir / "settings.toml"
        self._user_yarns_dir = self._config_dir / "yarns"
        self.all_yarns: dict[str, Yarn] = {}
        self._disabled_yarns: set[str] = set()
        self._settings: dict[str, dict[str, Any]] = {}
        self._initialized: bool = False

    def get_search_paths(self) -> list[Path]:
        """Return ordered search paths for yarn discovery."""
        return get_yarn_search_paths(config_dir=self._user_yarns_dir)

    def _register_module_yarns(self, mod: Any, override: bool = True) -> None:
        """Inspect a Python module and register all non-base Yarn subclasses."""
        for _, attr in inspect.getmembers(mod, inspect.isclass):
            if issubclass(attr, Yarn) and attr is not Yarn:
                try:
                    instance = attr()
                    with self._lock:
                        if override or instance.name not in self.all_yarns:
                            self.all_yarns[instance.name] = instance
                except SAFE_EXCEPTIONS as e:
                    logger.debug("skein.yarn_instantiation_failed", yarn_class=attr.__name__, error=str(e))

    def load_yarns_from_dir(self, target_dir: Path, override: bool = False) -> None:
        """Discover and register Yarns from a target directory."""
        if not target_dir.exists() or not target_dir.is_dir():
            return

        for py_file in target_dir.rglob("*.py"):
            if py_file.name.startswith("_"):
                continue
            if (
                py_file.parent != target_dir
                and py_file.stem != py_file.parent.name
                and not (py_file.parent / "pyproject.toml").exists()
            ):
                continue

            try:
                rel_stem = py_file.relative_to(target_dir).with_suffix("").as_posix().replace("/", "_")
                mod_name = f"textile_yarn_{rel_stem}"
                spec = importlib.util.spec_from_file_location(mod_name, py_file)
                if spec and spec.loader:
                    mod = importlib.util.module_from_spec(spec)
                    sys.modules[mod_name] = mod
                    spec.loader.exec_module(mod)
                    self._register_module_yarns(mod, override=override)
            except SAFE_EXCEPTIONS as e:
                logger.debug("skein.yarn_load_failed", path=str(py_file), error=str(e))

    def load_yarns(self) -> None:
        """Discover and register all Yarns across XDG search paths."""
        # Scan all standard search paths (in reverse order so higher-priority paths override lower-priority)
        for search_path in reversed(self.get_search_paths()):
            self.load_yarns_from_dir(search_path, override=True)

    def initialize(self) -> None:
        with self._lock:
            if self._initialized:
                return
            self._load_config()
            self.load_yarns()
            self._initialized = True

    def register_yarn(self, yarn: Yarn) -> None:
        with self._lock:
            self.all_yarns[yarn.name] = yarn

    def unregister_yarn(self, name: str) -> Yarn | None:
        with self._lock:
            return self.all_yarns.pop(name, None)

    def is_enabled(self, name: str) -> bool:
        with self._lock:
            return name not in self._disabled_yarns

    def toggle_yarn(self, name: str) -> bool:
        with self._lock:
            enabled = name in self._disabled_yarns
            self._disabled_yarns.discard(name) if enabled else self._disabled_yarns.add(name)
            self._save_config()
            return enabled

    def set_yarn_enabled(self, name: str, enabled: bool) -> None:
        with self._lock:
            self._disabled_yarns.discard(name) if enabled else self._disabled_yarns.add(name)
            self._save_config()

    def get_active_yarns(self) -> dict[str, Yarn]:
        self.initialize()
        with self._lock:
            active = {}
            for name, yarn in self.all_yarns.items():
                if name not in self._disabled_yarns:
                    try:
                        if yarn.is_available():
                            active[name] = yarn
                    except SAFE_EXCEPTIONS as e:
                        logger.debug("skein.yarn_availability_check_failed", yarn=name, error=str(e))
            return active

    def get_strand_by_name(self, strand_name: str) -> tuple[Yarn, Strand] | None:
        """Find registered active Yarn and Strand object for a given strand name."""
        active_yarns = self.get_active_yarns()
        for yarn in active_yarns.values():
            for strand_obj in yarn.get_strands():
                if strand_obj.name == strand_name:
                    return yarn, strand_obj
        return None

    def _load_config(self) -> None:
        try:
            if self._config_file.exists():
                self._disabled_yarns = set(orjson.loads(self._config_file.read_bytes()).get("disabled_yarns", []))
        except (OSError, orjson.JSONDecodeError, KeyError, TypeError) as e:
            logger.debug("skein.config_load_failed", path=str(self._config_file), error=str(e))

        self._load_settings()

    def _load_settings(self) -> None:
        try:
            if self._settings_file.exists():
                with self._settings_file.open("rb") as f:
                    parsed = tomllib.load(f)
                    if isinstance(parsed, dict):
                        self._settings = parsed
        except (OSError, tomllib.TOMLDecodeError) as e:
            logger.warning("skein.settings_load_failed", path=str(self._settings_file), error=str(e))
            self._settings = {}

    def get_yarn_settings(self, name: str) -> dict[str, Any]:
        self.initialize()
        with self._lock:
            data = self._settings.get(name, {})
            return dict(data) if isinstance(data, dict) else {}

    def get_yarn_settings_model(self, name: str) -> Any:
        """Retrieve validated Pydantic settings model for a yarn from active instances."""
        self.initialize()
        with self._lock:
            if name in self.all_yarns:
                return self.all_yarns[name].settings
        return self.get_yarn_settings(name)

    def set_yarn_settings(self, name: str, settings: dict[str, Any]) -> None:
        self.initialize()
        with self._lock:
            if settings:
                self._settings[name] = settings
            else:
                self._settings.pop(name, None)
            self._save_settings()
            if name in self.all_yarns:
                self.all_yarns[name].reload_settings()

    def get_all_settings(self) -> dict[str, Any]:
        self.initialize()
        with self._lock:
            return {k: dict(v) if isinstance(v, dict) else v for k, v in self._settings.items()}

    def get_all_yarn_schemas(self) -> dict[str, Any]:
        self.initialize()
        with self._lock:
            schemas: dict[str, Any] = {}
            for name, yarn_obj in self.all_yarns.items():
                schema = yarn_obj.get_settings_schema()
                if schema is not None:
                    schemas[name] = schema
                elif getattr(yarn_obj, "_settings_info", None):
                    schemas[name] = yarn_obj._settings_info
                elif getattr(yarn_obj, "_default_settings", None):
                    schemas[name] = yarn_obj._default_settings
            return schemas

    def generate_settings_template(self) -> str:
        return generate_documented_toml(self.get_all_yarn_schemas())

    def _save_config(self) -> None:
        try:
            self._config_file.parent.mkdir(parents=True, exist_ok=True)
            tmp_file = self._config_file.with_suffix(".tmp")
            payload = orjson.dumps({"disabled_yarns": list(self._disabled_yarns)}, option=orjson.OPT_INDENT_2)
            tmp_file.write_bytes(payload)
            tmp_file.replace(self._config_file)
        except (OSError, TypeError) as e:
            logger.warning("skein.config_save_failed", path=str(self._config_file), error=str(e))

    def _save_settings(self) -> None:
        try:
            self._settings_file.parent.mkdir(parents=True, exist_ok=True)
            tmp_file = self._settings_file.with_suffix(".tmp")

            schemas = self.get_all_yarn_schemas()
            if schemas:
                content = generate_documented_toml(schemas, current_settings=self._settings)
            else:
                content = _dumps_toml(self._settings)

            tmp_file.write_text(content, encoding="utf-8")
            tmp_file.replace(self._settings_file)
        except (OSError, TypeError) as e:
            logger.warning("skein.settings_save_failed", path=str(self._settings_file), error=str(e))


skein = Skein()

