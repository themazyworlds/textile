"""
Textile Skein - Layer 3 Symbolic Intent Compiler, Policy Engine, and Yarn Registry.
"""

import contextlib
import importlib
import importlib.util
import inspect
import json
import re
import sys
import threading
from importlib.metadata import entry_points
from pathlib import Path
from typing import Any

import textile.yarns
from textile.core.definitions.errors import SAFE_EXCEPTIONS
from textile.core.definitions.intent import IntentNode
from textile.core.definitions.manifest import YarnManifest
from textile.core.execution.strands import Strand
from textile.core.execution.yarn import Yarn
from textile.core.security.context import PolicyViolationError
from textile.core.telemetry.log import get_logger

logger = get_logger(__name__)

__all__ = ["PolicyViolationError", "Skein", "skein"]


class Skein:
    """Manages yarn discovery, intent compilation, policy verification, and runtime health."""

    def __init__(self, config_dir: Path | None = None):
        self._lock = threading.RLock()
        self._config_dir = config_dir or (Path.home() / ".config" / "textile")
        self._config_file = self._config_dir / "yarns.json"
        self._user_yarns_dir = self._config_dir / "yarns"
        self.all_yarns: dict[str, Yarn] = {}
        self._disabled_yarns: set[str] = set()
        self._initialized: bool = False

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

    def load_bundled_yarns(self) -> None:
        """Discover and load pre-installed Yarns directly from the textile.yarns package."""
        with contextlib.suppress(*SAFE_EXCEPTIONS):
            yarns_root = Path(textile.yarns.__file__).parent
            if not yarns_root.exists():
                return
            for py_file in yarns_root.rglob("*.py"):
                if py_file.name.startswith("_"):
                    continue
                try:
                    resolved_file = py_file.resolve()
                    resolved_root = yarns_root.resolve()
                    if not resolved_file.is_relative_to(resolved_root):
                        logger.warning("skein.yarn_path_traversal_blocked", path=str(py_file))
                        continue

                    rel_stem = py_file.relative_to(yarns_root).with_suffix("").as_posix().replace("/", ".")
                    if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*(\.[a-zA-Z_][a-zA-Z0-9_]*)*$", rel_stem):
                        logger.warning("skein.invalid_module_name_blocked", name=rel_stem)
                        continue

                    mod_name = f"textile.yarns.{rel_stem}"
                    spec = importlib.util.spec_from_file_location(mod_name, py_file)
                    if spec and spec.loader:
                        mod = importlib.util.module_from_spec(spec)
                        sys.modules[mod_name] = mod
                        spec.loader.exec_module(mod)
                        self._register_module_yarns(mod, override=True)
                except SAFE_EXCEPTIONS as e:
                    logger.debug("skein.bundled_yarn_load_failed", path=str(py_file), error=str(e))

    def load_yarns(self) -> None:
        """Discover and register all pre-installed, entrypoint, and custom Yarns."""
        # 1. Load bundled core Yarns directly from package directory
        self.load_bundled_yarns()

        # 2. PEP 621 Entry Point Yarns
        with contextlib.suppress(*SAFE_EXCEPTIONS):
            for ep in entry_points(group="textile.yarns"):
                with contextlib.suppress(*SAFE_EXCEPTIONS):
                    yarn_cls = ep.load()
                    if issubclass(yarn_cls, Yarn) and yarn_cls is not Yarn:
                        instance = yarn_cls()
                        with self._lock:
                            self.all_yarns[instance.name] = instance

        # 3. Load custom user Yarns from ~/.config/textile/yarns/ directory (without overwriting core bundled yarns)
        self.load_user_yarns()

    def load_user_yarns(self, yarn_dir: Path | None = None) -> None:
        """Discover and register Yarns from local user directory."""
        target_dir = yarn_dir or self._user_yarns_dir
        if not target_dir.exists():
            return
        for py_file in target_dir.rglob("*.py"):
            if py_file.name.startswith("_"):
                continue
            try:
                rel_stem = py_file.relative_to(target_dir).with_suffix("").as_posix().replace("/", "_")
                mod_name = f"textile_yarn_{rel_stem}"
                spec = importlib.util.spec_from_file_location(mod_name, py_file)
                if spec and spec.loader:
                    mod = importlib.util.module_from_spec(spec)
                    sys.modules[mod_name] = mod
                    spec.loader.exec_module(mod)
                    self._register_module_yarns(mod, override=False)
            except SAFE_EXCEPTIONS as e:
                logger.debug("skein.user_yarn_load_failed", path=str(py_file), error=str(e))

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

    def compile_and_execute_intent(self, intent: IntentNode) -> str:
        """Layer 3: Validate grammar and execute intent via central Loom dispatcher."""
        intent.validate_grammar()
        from textile.core.orchestration.loom import loom  # noqa: PLC0415

        return loom.execute_sync(intent.strand_name, intent.parameters, otp=intent.otp)

    def _load_config(self) -> None:
        try:
            if self._config_file.exists():
                self._disabled_yarns = set(json.loads(self._config_file.read_text()).get("disabled_yarns", []))
        except (OSError, json.JSONDecodeError, KeyError, TypeError) as e:
            logger.debug("skein.config_load_failed", path=str(self._config_file), error=str(e))

    def get_static_manifests(self) -> dict[str, YarnManifest]:
        """Statically inspect all TOML manifests without importing Python modules."""
        manifests: dict[str, YarnManifest] = {}
        dirs = [Path(__file__).parent.parent / "yarns"]
        if self._user_yarns_dir.exists():
            dirs.append(self._user_yarns_dir)

        for target_dir in dirs:
            for toml_file in target_dir.rglob("*.toml"):
                with contextlib.suppress(*SAFE_EXCEPTIONS):
                    m = YarnManifest.from_toml(toml_file)
                    if m.name:
                        manifests[m.name] = m
        return manifests

    def _save_config(self) -> None:
        try:
            self._config_file.parent.mkdir(parents=True, exist_ok=True)
            tmp_file = self._config_file.with_suffix(".tmp")
            tmp_file.write_text(json.dumps({"disabled_yarns": list(self._disabled_yarns)}, indent=2))
            tmp_file.replace(self._config_file)
        except (OSError, TypeError) as e:
            logger.warning("skein.config_save_failed", path=str(self._config_file), error=str(e))


skein = Skein()
