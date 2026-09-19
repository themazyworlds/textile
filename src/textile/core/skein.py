"""
Textile Skein - Yarn Discovery, Lifecycle, and Configuration Registry.
"""

import importlib
import importlib.util
import inspect
import json
import logging
import threading
from importlib.metadata import entry_points
from pathlib import Path

from textile.core.base import Yarn

logger = logging.getLogger(__name__)

BUILTIN_YARNS = [
    ("session.uwsm", "UWSM"),
    ("compositor.hyprland", "Hyprland"),
    ("compositor.caelestia", "Caelestia"),
    ("compositor.canvas", "Canvas"),
    ("protocols.clipboard", "Clipboard"),
    ("protocols.dbus_system", "DBus"),
    ("protocols.journal", "Journal"),
    ("protocols.polkit", "Polkit"),
    ("protocols.ydotool", "Ydotool"),
    ("protocols.atspi", "Atspi"),
    ("system_core.basics", "Basics"),
    ("system_core.process", "ProcessControl"),
    ("system_core.filesystem", "FilesystemStorage"),
    ("system_core.web_research", "WebResearch"),
    ("system_core.screen_vision", "ScreenVision"),
    ("system_core.dev_shell", "DevShell"),
    ("system_core.sensors", "Sensors"),
    ("system_core.packagekit", "PackageKit"),
]


class Skein:
    """Manages yarn discovery, configuration, and runtime health."""

    def __init__(self, config_dir: Path | None = None):
        self._lock = threading.RLock()
        self._config_dir = config_dir or (Path.home() / ".config" / "textile")
        self._config_file = self._config_dir / "yarns.json"
        self._user_yarns_dir = self._config_dir / "yarns"
        self.all_yarns: dict[str, Yarn] = {}
        self._disabled_yarns: set[str] = set()
        self._initialized: bool = False

    def initialize(self) -> None:
        with self._lock:
            if self._initialized:
                return
            self._load_config()
            self.load_builtin_yarns()
            self.load_entrypoint_yarns()
            self.load_user_yarns()
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

    def load_builtin_yarns(self) -> None:
        for mod_path, cls_name in BUILTIN_YARNS:
            try:
                mod = importlib.import_module(f"textile.yarns.{mod_path}")
                instance = getattr(mod, cls_name)()
                with self._lock:
                    self.all_yarns[instance.name] = instance
            except (ImportError, AttributeError, TypeError, ValueError, KeyError, OSError, RuntimeError) as e:
                logger.debug(f"Skipping builtin yarn {mod_path}: {e}")

    def load_entrypoint_yarns(self) -> None:
        try:
            for ep in entry_points(group="textile.yarns"):
                try:
                    yarn_cls = ep.load()
                    if issubclass(yarn_cls, Yarn):
                        instance = yarn_cls()
                        with self._lock:
                            self.all_yarns[instance.name] = instance
                except (ImportError, AttributeError, TypeError, ValueError, KeyError, OSError, RuntimeError) as e:
                    logger.debug(f"Failed loading entrypoint yarn {ep}: {e}")
        except (ImportError, AttributeError, TypeError, ValueError, KeyError, OSError, RuntimeError) as e:
            logger.debug(f"Failed scanning entrypoints: {e}")

    def load_user_yarns(self, yarn_dir: Path | None = None) -> None:
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
                    for _, attr in inspect.getmembers(mod, inspect.isclass):
                        if issubclass(attr, Yarn) and attr is not Yarn:
                            instance = attr()
                            with self._lock:
                                self.all_yarns[instance.name] = instance
            except (ImportError, AttributeError, TypeError, ValueError, KeyError, OSError, RuntimeError) as e:
                logger.debug(f"Failed loading user yarn {py_file}: {e}")

    def _load_config(self) -> None:
        try:
            if self._config_file.exists():
                self._disabled_yarns = set(json.loads(self._config_file.read_text()).get("disabled_yarns", []))
        except (OSError, json.JSONDecodeError, KeyError, TypeError) as e:
            logger.debug(f"Could not load skein config: {e}")

    def _save_config(self) -> None:
        try:
            self._config_file.parent.mkdir(parents=True, exist_ok=True)
            self._config_file.write_text(json.dumps({"disabled_yarns": list(self._disabled_yarns)}, indent=2))
        except (OSError, TypeError) as e:
            logger.warning(f"Could not save skein config: {e}")


skein = Skein()

