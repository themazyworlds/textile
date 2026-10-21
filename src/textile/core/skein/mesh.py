"""
Textile Skein - Layer 3 Symbolic Intent Compiler, Policy Engine, and Yarn Registry.
"""

import importlib.util
import inspect
import sys
import threading
import tomllib
from pathlib import Path
from typing import Any, get_args, get_origin
lazy import importlib.metadata

import orjson
from needle import Yarn
from needle.errors import SAFE_EXCEPTIONS
lazy from needle import Strand
lazy from pydantic import BaseModel
lazy from pydantic_core import PydanticUndefined

lazy from textile.core.camshaft import camshaft
lazy from textile.core.fabric import core_fabric_yarn
lazy from textile.core.skein.discovery import find_yarn_files, get_yarn_search_paths, probe_isolated_yarn

__all__ = ["Skein", "SkeinMesh", "skein", "skein_mesh"]


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
                    camshaft.stitch_notice(
                        level="DEBUG",
                        source="skein",
                        message=f"Failed to instantiate yarn class '{attr.__name__}': {e}",
                        data={"yarn_class": attr.__name__, "error": str(e)},
                    )

    def load_yarns_from_dir(self, target_dir: Path, override: bool = False) -> None:
        """Discover and register Yarns from a target directory."""
        if not target_dir.exists() or not target_dir.is_dir():
            return

        for py_file in find_yarn_files(target_dir):
            # 1. Prefer isolated venv probe with schema disk cache when private venv exists
            probed_inst = probe_isolated_yarn(py_file)
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
                camshaft.stitch_notice(
                    level="DEBUG",
                    source="skein",
                    message=f"Failed in-process load of '{py_file}': {e}",
                    data={"path": str(py_file), "error": str(e)},
                )

    def load_entry_point_yarns(self) -> None:
        """Discover and register Yarns via standard PEP 621 entry points (textile.yarns)."""
        try:
            discovered = importlib.metadata.entry_points(group="textile.yarns")
        except SAFE_EXCEPTIONS as e:
            camshaft.stitch_notice(
                level="DEBUG",
                source="skein",
                message=f"Entry points query failed: {e}",
                data={"error": str(e)},
            )
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
                camshaft.stitch_notice(
                    level="DEBUG",
                    source="skein",
                    message=f"Entry point load failed for '{ep.name}': {e}",
                    data={"name": ep.name, "error": str(e)},
                )

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
            if "core" not in self.all_yarns:
                self.register_yarn(core_fabric_yarn)
            self.load_yarns()
            self._initialized = True

    def reload_plugins(self) -> None:
        """Reload all discovered plugins from disk and notify engine."""
        with self._lock:
            self._initialized = False
        self.initialize()
        camshaft.emit("yarn_status_changed", sender="skein")

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

    def get_yarn(self, name: str) -> Yarn | None:
        """Resolve a specific yarn by name."""
        self.initialize()
        return self.all_yarns.get(name)

    def get_all_yarns(self) -> dict[str, Yarn]:
        """Retrieve all registered yarns."""
        self.initialize()
        return dict(self.all_yarns)

    def is_enabled(self, name: str) -> bool:
        with self._lock:
            return name not in self._disabled_yarns

    def toggle_yarn(self, name: str) -> bool:
        self.initialize()
        with self._lock:
            was_disabled = name in self._disabled_yarns
            if was_disabled:
                self._disabled_yarns.discard(name)
                new_state = True
            else:
                self._disabled_yarns.add(name)
                new_state = False
            self._save_config()
            return new_state

    def set_yarn_enabled(self, name: str, enabled: bool) -> None:
        self.initialize()
        with self._lock:
            if enabled:
                self._disabled_yarns.discard(name)
            else:
                self._disabled_yarns.add(name)
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
                        camshaft.stitch_notice(
                            level="DEBUG",
                            source="skein",
                            message=f"Yarn availability check failed for '{name}': {e}",
                            data={"yarn": name, "error": str(e)},
                        )
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
            camshaft.stitch_notice(
                level="DEBUG",
                source="skein",
                message=f"Config load failed for '{self._config_file}': {e}",
                data={"path": str(self._config_file), "error": str(e)},
            )

        self._load_settings()

    def _load_settings(self) -> None:
        try:
            if self._settings_file.exists():
                with self._settings_file.open("rb") as f:
                    parsed = tomllib.load(f)
                    if isinstance(parsed, dict):
                        self._settings = parsed
        except (OSError, tomllib.TOMLDecodeError) as e:
            camshaft.stitch_notice(
                level="WARNING",
                source="skein",
                message=f"Settings load failed for '{self._settings_file}': {e}",
                data={"path": str(self._settings_file), "error": str(e)},
            )
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
                settings_info = getattr(yarn_obj, "_settings_info", None)
                default_settings = getattr(yarn_obj, "_default_settings", None)
                if schema is not None:
                    schemas[name] = schema
                elif settings_info:
                    schemas[name] = settings_info
                elif default_settings:
                    schemas[name] = default_settings
            return schemas

    get_settings_schemas = get_all_yarn_schemas

    def generate_settings_template(self) -> str:
        return _generate_documented_toml(self.get_all_yarn_schemas())

    generate_documented_toml = generate_settings_template

    def _save_config(self) -> None:
        try:
            self._config_file.parent.mkdir(parents=True, exist_ok=True)
            tmp_file = self._config_file.with_suffix(".tmp")
            payload = orjson.dumps({"disabled_yarns": list(self._disabled_yarns)}, option=orjson.OPT_INDENT_2)
            tmp_file.write_bytes(payload)
            tmp_file.replace(self._config_file)
        except (OSError, TypeError) as e:
            camshaft.stitch_notice(
                level="WARNING",
                source="skein",
                message=f"Config save failed for '{self._config_file}': {e}",
                data={"path": str(self._config_file), "error": str(e)},
            )

    def _save_settings(self) -> None:
        try:
            self._settings_file.parent.mkdir(parents=True, exist_ok=True)
            tmp_file = self._settings_file.with_suffix(".tmp")

            schemas = self.get_all_yarn_schemas()
            if schemas:
                content = _generate_documented_toml(schemas, current_settings=self._settings)
            else:
                content = _dumps_toml(self._settings)

            tmp_file.write_text(content, encoding="utf-8")
            tmp_file.replace(self._settings_file)
        except (OSError, TypeError) as e:
            camshaft.stitch_notice(
                level="WARNING",
                source="skein",
                message=f"Settings save failed for '{self._settings_file}': {e}",
                data={"path": str(self._settings_file), "error": str(e)},
            )


skein = Skein()
skein_mesh = skein
SkeinMesh = Skein


@camshaft.on("yarn_toggle_input")
def _on_yarn_toggle_input(_sender: Any = None, *, yarn_name: str, **_kw: Any) -> bool:
    state = skein.toggle_yarn(yarn_name)
    camshaft.emit("yarn_status_changed", sender="skein", yarn_name=yarn_name, enabled=state)
    return state


def _format_type_name(annotation: Any) -> str:
    """Format Python type annotations into human-friendly strings."""
    if annotation is None or annotation is type(None):
        return "none"

    origin = get_origin(annotation)
    args = get_args(annotation)

    if origin is None:
        return annotation.__name__ if isinstance(annotation, type) else str(annotation)

    origin_name = getattr(origin, "__name__", str(origin)).lower()
    if "union" in origin_name:
        non_none = [a for a in args if a is not type(None)]
        return (
            f"optional[{_format_type_name(non_none[0])}]"
            if len(non_none) == 1
            else " | ".join(_format_type_name(a) for a in args)
        )

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
        formatted = f'"{escaped}"'
    elif isinstance(val, (list, tuple, set)):
        items = ", ".join(_format_toml_literal(x) for x in val)
        formatted = f"[{items}]"
    elif isinstance(val, dict):
        items = ", ".join(f"{k} = {_format_toml_literal(v)}" for k, v in val.items())
        formatted = f"{{{items}}}"
    else:
        formatted = f'"{val}"'
    return formatted


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


def _generate_documented_toml(
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


def _dumps_toml(data: dict[str, Any]) -> str:
    """Format an arbitrary settings dictionary into valid TOML format."""
    lines: list[str] = [
        "# Textile settings",
        "# Edit any setting below to customize per-yarn configuration.",
        "",
    ]
    top_level = [f"{k} = {_format_toml_literal(v)}" for k, v in data.items() if not isinstance(v, dict)]
    if top_level:
        lines.extend(top_level)
        lines.append("")

    for section, table in data.items():
        if isinstance(table, dict):
            lines.append(f"[{section}]")
            for k, v in table.items():
                lines.append(f"{k} = {_format_toml_literal(v)}")
            lines.append("")

    return "\n".join(lines).strip() + "\n"
