"""
Textile Skein - Layer 3 Symbolic Intent Compiler, Policy Engine, and Yarn Registry.
"""

import contextlib
import importlib
import importlib.util
import inspect
import json
import logging
import threading
from importlib.metadata import entry_points
from pathlib import Path
from typing import Any

import textile.yarns
from textile import Strand, Yarn, YarnManifest
from textile.core.context import PolicyViolationError, verify_security_policy
from textile.core.intent import IntentNode, IntentValidationError
from textile.core.transaction import Transaction, transaction_stack

logger = logging.getLogger(__name__)

__all__ = ["PolicyViolationError", "Skein", "skein"]


MODULE_LOAD_ERRORS = (ImportError, AttributeError, TypeError, ValueError, KeyError, OSError, RuntimeError)


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

    def _register_module_yarns(self, mod: Any) -> None:
        """Inspect a Python module and register all non-base Yarn subclasses."""
        for _, attr in inspect.getmembers(mod, inspect.isclass):
            if issubclass(attr, Yarn) and attr is not Yarn:
                try:
                    instance = attr()
                    with self._lock:
                        self.all_yarns[instance.name] = instance
                except MODULE_LOAD_ERRORS as e:
                    logger.debug(f"Failed instantiating yarn {attr}: {e}")

    def load_yarns(self) -> None:
        """Discover and register all package, entrypoint, and custom Yarns."""
        # 1. Package Yarns under textile.yarns namespace
        with contextlib.suppress(*MODULE_LOAD_ERRORS):
            yarns_root = Path(textile.yarns.__file__).parent
            for py_file in yarns_root.rglob("*.py"):
                if py_file.name.startswith("_"):
                    continue
                rel_path = py_file.relative_to(yarns_root).with_suffix("").as_posix().replace("/", ".")
                modname = f"textile.yarns.{rel_path}"
                with contextlib.suppress(*MODULE_LOAD_ERRORS):
                    self._register_module_yarns(importlib.import_module(modname))

        # 2. PEP 621 Entry Point Yarns
        with contextlib.suppress(*MODULE_LOAD_ERRORS):
            for ep in entry_points(group="textile.yarns"):
                with contextlib.suppress(*MODULE_LOAD_ERRORS):
                    yarn_cls = ep.load()
                    if issubclass(yarn_cls, Yarn) and yarn_cls is not Yarn:
                        instance = yarn_cls()
                        with self._lock:
                            self.all_yarns[instance.name] = instance

        # 3. User Custom Yarns (~/.config/textile/yarns/*.py)
        self.load_user_yarns()

    def load_user_yarns(self, yarn_dir: Path | None = None) -> None:
        """Discover and register custom user Yarns from local directory."""
        target_dir = yarn_dir or self._user_yarns_dir
        if not target_dir.exists():
            return
        for py_file in target_dir.glob("*.py"):
            if py_file.name.startswith("_"):
                continue
            try:
                spec = importlib.util.spec_from_file_location(f"textile_user_{py_file.stem}", py_file)
                if spec and spec.loader:
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)
                    self._register_module_yarns(mod)
            except (ImportError, AttributeError, TypeError, ValueError, KeyError, OSError, RuntimeError) as e:
                logger.debug(f"Failed loading user yarn {py_file}: {e}")

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
                    except (AttributeError, TypeError, ValueError, KeyError, OSError, RuntimeError) as e:
                        logger.debug(f"Yarn '{name}' availability check failed: {e}")
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
        """Layer 3: Validate grammar, verify origin security policy, compile intent, and execute."""
        # 1. Grammar & Injection Sanitization
        intent.validate_grammar()

        # 2. Resolve Strand
        target = self.get_strand_by_name(intent.strand_name)
        if not target:
            raise IntentValidationError(f"Strand '{intent.strand_name}' is not registered or active.")

        _, target_strand = target

        # 3. Layer 3 Policy Verification — canonical single-source-of-truth gate.
        verify_security_policy(intent.origin_token, target_strand.tier, target_strand.name)

        # 4. Execution
        if target_strand.handler is None:
            raise IntentValidationError(f"Strand '{target_strand.name}' has no registered handler.")

        res = target_strand.handler(intent.parameters)

        # 5. Layer 4: Register state-mutating transactions on the undo stack
        if target_strand.tier in ("mutate", "privileged", "system_exec"):
            transaction_stack.push(
                Transaction(
                    strand_name=target_strand.name,
                    parameters=intent.parameters,
                    result_data=res,
                )
            )

        return str(res) if res is not None else "ok"

    def _load_config(self) -> None:
        try:
            if self._config_file.exists():
                self._disabled_yarns = set(json.loads(self._config_file.read_text()).get("disabled_yarns", []))
        except (OSError, json.JSONDecodeError, KeyError, TypeError) as e:
            logger.debug(f"Could not load skein config: {e}")

    def get_static_manifests(self) -> dict[str, YarnManifest]:
        """Statically inspect all TOML manifests without importing Python modules."""
        manifests: dict[str, YarnManifest] = {}
        dirs = [Path(__file__).parent.parent / "yarns"]
        if self._user_yarns_dir.exists():
            dirs.append(self._user_yarns_dir)

        for target_dir in dirs:
            for toml_file in target_dir.rglob("*.toml"):
                with contextlib.suppress(OSError, ValueError, TypeError, KeyError, AttributeError, RuntimeError):
                    m = YarnManifest.from_toml(toml_file)
                    if m.name:
                        manifests[m.name] = m
        return manifests

    def _save_config(self) -> None:
        try:
            self._config_file.parent.mkdir(parents=True, exist_ok=True)
            self._config_file.write_text(json.dumps({"disabled_yarns": list(self._disabled_yarns)}, indent=2))
        except (OSError, TypeError) as e:
            logger.warning(f"Could not save skein config: {e}")


skein = Skein()
