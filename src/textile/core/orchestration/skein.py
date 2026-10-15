"""
Textile Skein - Layer 3 Symbolic Intent Compiler, Policy Engine, and Yarn Registry.
"""

import importlib.metadata
import importlib.util
import inspect
import sys
import threading
import tomllib
from pathlib import Path
from typing import Any

import orjson
from needle import Strand, Yarn
from needle.errors import SAFE_EXCEPTIONS

from textile.core.definitions.errors import PolicyViolationError
from textile.core.definitions.settings import dumps_toml, generate_documented_toml
from textile.core.orchestration.discovery import (
    find_yarn_files,
    get_yarn_search_paths,
    try_probe_isolated_yarn,
)
from textile.core.telemetry.log import get_logger

logger = get_logger(__name__)

__all__ = ["PolicyViolationError", "Skein", "get_yarn_search_paths", "skein"]


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

        for py_file in find_yarn_files(target_dir):
            # 1. Prefer isolated venv probe with schema disk cache when private venv exists
            probed_inst = try_probe_isolated_yarn(py_file)
            if probed_inst is not None:
                with self._lock:
                    if override or probed_inst.name not in self.all_yarns:
                        self.all_yarns[probed_inst.name] = probed_inst
                continue

            # 2. Otherwise try in-process import
            try:
                rel_stem = py_file.relative_to(target_dir).with_suffix("").as_posix().replace("/", "_")
                mod_name = f"textile_yarn_{rel_stem}"
                spec = importlib.util.spec_from_file_location(mod_name, py_file)
                if spec and spec.loader:
                    mod = importlib.util.module_from_spec(spec)
                    sys.modules[mod_name] = mod
                    spec.loader.exec_module(mod)
                    self._register_module_yarns(mod, override=override)
                    continue
            except SAFE_EXCEPTIONS as e:
                logger.debug("skein.yarn_inprocess_load_failed", path=str(py_file), error=str(e))

    def load_entry_point_yarns(self) -> None:
        """Discover and register Yarns via standard PEP 621 entry points (textile.yarns)."""
        try:
            discovered = importlib.metadata.entry_points(group="textile.yarns")
        except SAFE_EXCEPTIONS as e:
            logger.debug("skein.entry_points_query_failed", error=str(e))
            return

        for ep in discovered:
            try:
                loaded = ep.load()
                if isinstance(loaded, type) and issubclass(loaded, Yarn) and loaded is not Yarn:
                    instance = loaded()
                    with self._lock:
                        if instance.name not in self.all_yarns:
                            self.all_yarns[instance.name] = instance
                elif isinstance(loaded, Yarn):
                    with self._lock:
                        if loaded.name not in self.all_yarns:
                            self.all_yarns[loaded.name] = loaded
            except SAFE_EXCEPTIONS as e:
                logger.debug("skein.entry_point_load_failed", name=ep.name, error=str(e))

    def load_yarns(self) -> None:
        """Discover and register all Yarns across entry points and XDG search paths."""
        self.load_entry_point_yarns()
        for search_path in self.get_search_paths():
            self.load_yarns_from_dir(search_path, override=False)

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
            if yarn.name in self._settings:
                if hasattr(yarn, "set_user_settings"):
                    yarn.set_user_settings(self._settings[yarn.name])
                else:
                    yarn._user_settings = dict(self._settings[yarn.name])
                    yarn.reload_settings()

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
                yarn_instance = self.all_yarns[name]
                if hasattr(yarn_instance, "set_user_settings"):
                    yarn_instance.set_user_settings(settings)
                else:
                    yarn_instance._user_settings = dict(settings)
                    yarn_instance.reload_settings()

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
                content = dumps_toml(self._settings)

            tmp_file.write_text(content, encoding="utf-8")
            tmp_file.replace(self._settings_file)
        except (OSError, TypeError) as e:
            logger.warning("skein.settings_save_failed", path=str(self._settings_file), error=str(e))


skein = Skein()
