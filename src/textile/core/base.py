"""
Textile Core Yarn & Strand System - Base Interfaces & Definitions.
"""

import inspect
import json
import logging
import os
import pwd
import re
import shutil
import subprocess
import sys
import tomllib
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal, get_type_hints

from pydantic import BaseModel, Field, ValidationError, create_model

from textile.core.sandbox import BubblewrapSandbox
from textile.core.tapestry import sensory_tapestry
from textile.core.warp import warp

logger = logging.getLogger(__name__)

# Standard Layer Tiers (Higher number = outer layer with higher override authority)
LAYER_BASE = 10                # Base OS / Pure POSIX kernel fallbacks
LAYER_DESKTOP_PROTOCOL = 50   # Generic Wayland, XDG, D-Bus protocols
LAYER_COMPOSITOR_DE = 100     # Specific Compositors & DEs (Hyprland, Caelestia, GNOME, KDE)
LAYER_SESSION_MANAGER = 150   # Session Managers & Cgroup Wrappers (UWSM, systemd-run)
LAYER_USER_OVERRIDE = 1000    # User custom overrides (~/.config/textile/yarns/)

STRAND_EXEC_ERRORS = (
    AttributeError,
    TypeError,
    ValueError,
    KeyError,
    OSError,
    RuntimeError,
    json.JSONDecodeError,
)


class CapabilityTier(StrEnum):
    """Execution risk & privilege tiers for Textile Strands."""
    OBSERVE = "observe"         # Read-only telemetry, state inspection, queries, logs
    INTERACT = "interact"       # Desktop GUI interactions, notifications, clipboard, media
    MUTATE = "mutate"           # File modifications, killing user processes, local workspace changes
    PRIVILEGED = "privileged"   # System configuration, package installs, D-Bus system calls, Polkit
    SYSTEM_EXEC = "system_exec" # Arbitrary shell command execution (auto-isolated)


def detects_native_ffi(target: Any) -> bool:
    """Detect if a class or module imports native C-FFI modules (ctypes, cffi)."""
    try:
        mod_name = target.__class__.__module__ if hasattr(target, "__class__") else getattr(target, "__module__", "")
        mod = sys.modules.get(mod_name)
        if mod:
            for val in mod.__dict__.values():
                if getattr(val, "__name__", "") in ("ctypes", "cffi", "_ctypes"):
                    return True
                if isinstance(val, type) and getattr(val, "__module__", "") in ("ctypes", "cffi", "_ctypes"):
                    return True
    except (AttributeError, TypeError, ValueError, RuntimeError) as e:
        logger.debug(f"detects_native_ffi inspection error: {e}")
    return False


def resolve_terminal_and_shell() -> tuple[str, str]:
    term = os.environ.get("TERM", "xterm-256color")
    shell_path = pwd.getpwuid(os.getuid()).pw_shell
    if not (os.path.isfile(shell_path) and os.access(shell_path, os.X_OK)):
        raise RuntimeError("Shell binary not accessible on disk.")
    return term, shell_path


def schema_to_model(strand_name: str, parameters: dict[str, Any], required: list[str]) -> type[BaseModel]:
    """Dynamically synthesize a Pydantic BaseModel from JSON schema parameters."""
    fields: dict[str, Any] = {}
    type_map = {"string": str, "integer": int, "number": float, "boolean": bool, "array": list, "object": dict}
    for p_name, p_spec in (parameters or {}).items():
        desc = p_spec.get("description", "")
        enum_vals = p_spec.get("enum")
        t_str = str(p_spec.get("type", "string")).lower()
        field_type: Any = Literal[tuple(enum_vals)] if enum_vals else type_map.get(t_str, Any)  # type: ignore
        if p_name in (required or []):
            fields[p_name] = (field_type, Field(..., description=desc))
        else:
            fields[p_name] = (field_type | None, Field(default=None, description=desc))
    return create_model(f"{strand_name}_Args", **fields)


@dataclass
class Strand:
    """Represents a single callable tool/strand exposed by a yarn."""

    name: str
    description: str
    parameters: dict[str, Any] = field(default_factory=dict)
    handler: Callable[[dict[str, Any]], str] | None = None
    required: list[str] = field(default_factory=list)
    raw_handler: Callable[[dict[str, Any]], Any] | None = None
    capability: str | None = None
    args_schema: type[BaseModel] | None = None
    tier: CapabilityTier = CapabilityTier.INTERACT
    isolated: bool = False
    resources: list[str] = field(default_factory=list)

    def to_mcp_definition(self) -> dict[str, Any]:
        """Convert strand schema into Model Context Protocol format."""
        tier_str = str(self.tier.value).upper() if hasattr(self.tier, "value") else str(self.tier).upper()
        desc = f"[Capability Tier: {tier_str}] {self.description}"
        if self.args_schema:
            return {
                "name": self.name,
                "description": desc,
                "inputSchema": self.args_schema.model_json_schema(),
            }
        return {
            "name": self.name,
            "description": desc,
            "inputSchema": {
                "type": "object",
                "properties": self.parameters,
                "required": self.required,
                "additionalProperties": False,
            },
        }


@dataclass
class Weft:
    """Represents a streaming semantic token interceptor / attunement declared by a yarn."""

    name: str
    pattern: re.Pattern
    description: str
    strip: bool = True
    priority: int = 100
    handler: Callable[..., Any] | None = None
    raw_handler: Callable[..., Any] | None = None
    args_schema: type[BaseModel] | None = None
    param_names: list[str] = field(default_factory=list)

    def execute_match(self, match: re.Match) -> Any:
        """Execute weft attunement handler with regex match extracted arguments coerced with Pydantic."""
        raw_kwargs: dict[str, Any] = {}
        named = {k: v for k, v in match.groupdict().items() if v is not None}
        if named:
            raw_kwargs = named
        elif match.groups():
            raw_kwargs = dict(zip(self.param_names, match.groups()))
        elif len(self.param_names) == 1:
            raw_kwargs = {self.param_names[0]: match.group(0)}

        if self.args_schema:
            try:
                validated = self.args_schema.model_validate(raw_kwargs)
                coerced = validated.model_dump()
            except ValidationError as e:
                logger.warning(f"Weft '{self.name}' argument coercion failed: {e}")
                coerced = raw_kwargs
        else:
            coerced = raw_kwargs

        if self.handler:
            return self.handler(**coerced)
        return None


def validate_strand_schema(strand_name: str, parameters: Any, required: Any) -> list[str]:
    errors = []
    if not isinstance(parameters, dict):
        return [f"Strand '{strand_name}' parameters must be a dictionary."]
    valid_types = {"string", "number", "integer", "boolean", "array", "object"}
    for p_name, p_spec in parameters.items():
        if not isinstance(p_spec, dict) or str(p_spec.get("type", "")).lower() not in valid_types:
            errors.append(f"Parameter '{p_name}' has invalid specification.")
    if isinstance(required, list):
        for req in required:
            if req not in parameters:
                errors.append(f"Required field '{req}' not in parameters.")
    return errors


def validate_strand_arguments(
    strand_name: str,
    args: dict[str, Any],
    schema_model: type[BaseModel] | None = None,
    parameters: dict[str, Any] | None = None,
    required: list[str] | None = None,
) -> tuple[str | None, dict[str, Any]]:
    """Strictly validates arguments using Pydantic v2."""
    model = schema_model
    if not model:
        if not parameters:
            return None, args
        try:
            model = schema_to_model(strand_name, parameters, required or [])
        except (AttributeError, TypeError, ValueError, KeyError, ValidationError):
            return None, args

    clean_args = dict(args or {})
    if required:
        for r in required:
            if r in clean_args and isinstance(clean_args[r], str) and not clean_args[r].strip():
                p_type = (parameters or {}).get(r, {}).get("type", "value")
                return (
                    f"Validation Hint: Strand '{strand_name}' expected required parameter '{r}' "
                    f"(type: {p_type}), but it went missing in action!",
                    args,
                )

    try:
        validated = model.model_validate(clean_args)
        return None, {k: v for k, v in validated.model_dump().items() if v is not None}
    except ValidationError as e:
        err = e.errors()[0]
        loc = str(err["loc"][0]) if err["loc"] else "parameter"
        err_type = err["type"]
        p_type = (parameters or {}).get(loc, {}).get("type", "value")
        if "missing" in err_type:
            msg = (
                f"Validation Hint: Strand '{strand_name}' expected required parameter '{loc}' "
                f"(type: {p_type}), but it went missing in action!"
            )
        elif "literal" in err_type or "enum" in err_type:
            expected = err.get("ctx", {}).get("expected", "")
            msg = (
                f"Validation Hint: Invalid action/option '{args.get(loc)}' for strand '{strand_name}'. "
                f"Available options: [{expected}]"
            )
        else:
            msg = f"Validation Hint: Strand '{strand_name}' parameter '{loc}' validation failed: {err['msg']}."
        return msg, args


def _extract_docstring_info(doc: str | None) -> tuple[str, dict[str, str]]:
    if not doc:
        return "", {}
    desc_lines, param_docs = [], {}
    for line in doc.strip().splitlines():
        s = line.strip()
        m = re.match(r":param\s+([a-zA-Z0-9_]+):\s*(.*)", s) or re.match(r"([a-zA-Z0-9_]+)(?:\s*\([^)]*\))?:\s+(.*)", s)
        if m and not s.startswith(("http:", "https:", "Note:", "Warning:", "Returns:", "Yields:")):
            param_docs[m.group(1)] = m.group(2)
        elif not param_docs:
            desc_lines.append(s)
    return " ".join(desc_lines).strip(), param_docs


def strand(
    func: Callable | None = None,
    *,
    name: str | None = None,
    description: str | None = None,
    capability: str | None = None,
    tier: CapabilityTier | str = CapabilityTier.INTERACT,
    isolated: bool | None = None,
    timeout: float = 30.0,
):
    """Decorator marking a Yarn method as an executable Desktop Strand."""
    def decorator(fn: Any) -> Any:
        setattr(fn, "_is_strand", True)
        setattr(fn, "_strand_name", name or getattr(fn, "__name__", ""))
        setattr(fn, "_strand_description", description)
        setattr(fn, "_strand_capability", capability)
        setattr(fn, "_strand_tier", tier)
        setattr(fn, "_strand_isolated", isolated)
        setattr(fn, "_strand_timeout", timeout)
        return fn

    return decorator(func) if func is not None else decorator


def weft(
    func: Callable | None = None,
    *,
    pattern: str | re.Pattern,
    name: str | None = None,
    description: str | None = None,
    strip: bool = True,
    priority: int = 100,
):
    """Decorator marking a Yarn method as a real-time streaming token Weft attunement."""
    compiled_pattern = re.compile(pattern) if isinstance(pattern, str) else pattern

    def decorator(fn: Any) -> Any:
        setattr(fn, "_is_weft", True)
        setattr(fn, "_weft_name", name or getattr(fn, "__name__", ""))
        setattr(fn, "_weft_pattern", compiled_pattern)
        setattr(fn, "_weft_description", description)
        setattr(fn, "_weft_strip", strip)
        setattr(fn, "_weft_priority", priority)
        return fn

    return decorator(func) if func is not None else decorator


def _parse_tier(raw_tier: Any) -> CapabilityTier:
    if isinstance(raw_tier, CapabilityTier):
        return raw_tier
    if isinstance(raw_tier, str):
        try:
            return CapabilityTier(raw_tier.lower())
        except ValueError:
            pass
    return CapabilityTier.INTERACT


async def _exec_async_strand(
    method: Callable,
    strand_name: str,
    args: dict[str, Any],
    args_model: type[BaseModel] | None,
    params: dict[str, Any],
    req_list: list[str],
) -> str:
    val_err, coerced = validate_strand_arguments(
        strand_name, args, schema_model=args_model, parameters=params, required=req_list
    )
    if val_err:
        return val_err
    try:
        res = await method(**coerced)
        if isinstance(res, (dict, list)):
            return json.dumps(res, indent=2)
        return str(res) if res is not None else "ok"
    except STRAND_EXEC_ERRORS as e:
        return f"Error executing strand '{strand_name}': {e}"


def _exec_sync_strand(
    yarn: Any,
    method: Callable,
    strand_name: str,
    args: dict[str, Any],
    args_model: type[BaseModel] | None,
    params: dict[str, Any],
    req_list: list[str],
    isolated: bool,
    timeout: float,
    tier: CapabilityTier = CapabilityTier.INTERACT,
) -> str:
    val_err, coerced = validate_strand_arguments(
        strand_name, args, schema_model=args_model, parameters=params, required=req_list
    )
    if val_err:
        return val_err
    if isolated:
        return yarn._run_isolated(strand_name, coerced, timeout=timeout, tier=tier)
    try:
        res = method(**coerced)
        if isinstance(res, (dict, list)):
            return json.dumps(res, indent=2)
        return str(res) if res is not None else "ok"
    except STRAND_EXEC_ERRORS as e:
        return f"Error executing strand '{strand_name}': {e}"


def _create_invoker(
    yarn: Any,
    method: Callable,
    strand_name: str,
    args_model: type[BaseModel] | None,
    params: dict[str, Any],
    req_list: list[str],
    isolated: bool,
    is_async: bool,
    timeout: float,
    tier: CapabilityTier = CapabilityTier.INTERACT,
) -> Callable[[dict[str, Any]], Any]:
    if is_async:
        async def _async_invoker(args: dict[str, Any]) -> str:
            return await _exec_async_strand(method, strand_name, args, args_model, params, req_list)

        return _async_invoker

    def _sync_invoker(args: dict[str, Any]) -> str:
        return _exec_sync_strand(
            yarn, method, strand_name, args, args_model, params, req_list, isolated, timeout, tier
        )

    return _sync_invoker


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
    contract: str = ""
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


class Yarn(ABC):
    """Abstract Base Class for all Textile Capability Yarns."""

    manifest: YarnManifest

    def __init__(self, manifest: YarnManifest | None = None) -> None:
        if manifest is not None:
            self.manifest = manifest
            return

        mod_file = getattr(sys.modules.get(self.__class__.__module__), "__file__", None)
        if mod_file:
            p = Path(mod_file)
            toml_file = p.with_suffix(".toml")
            if not toml_file.exists():
                toml_file = p.parent / "yarn.toml"
            if toml_file.exists():
                self.manifest = YarnManifest.from_toml(toml_file)
                return

        raise FileNotFoundError(
            f"Validation Hint: Yarn '{self.__class__.__name__}' requires a valid TOML manifest file "
            "(<name>.toml or yarn.toml)."
        )

    @property
    def name(self) -> str:
        return self.manifest.name

    @name.setter
    def name(self, value: str) -> None:
        self.manifest.name = value

    @property
    def publisher(self) -> str:
        return self.manifest.publisher

    @publisher.setter
    def publisher(self, value: str) -> None:
        self.manifest.publisher = value

    @property
    def version(self) -> str:
        return self.manifest.version

    @version.setter
    def version(self, value: str) -> None:
        self.manifest.version = value

    @property
    def description(self) -> str:
        return self.manifest.description

    @description.setter
    def description(self, value: str) -> None:
        self.manifest.description = value

    @property
    def layer(self) -> int:
        return self.manifest.layer

    @layer.setter
    def layer(self, value: int) -> None:
        self.manifest.layer = value

    @property
    def python_dependencies(self) -> list[str]:
        return self.manifest.python_dependencies

    @python_dependencies.setter
    def python_dependencies(self, value: list[str]) -> None:
        self.manifest.python_dependencies = value

    def get_contract(self) -> str | None:
        """Return the yarn's sealed contract / advisory letter for the AI client."""
        if self.manifest and self.manifest.contract:
            return self.manifest.contract
        return getattr(self, "contract", None) or (self.__doc__.strip() if self.__doc__ else None)

    def get_python_dependencies(self) -> list[str]:
        """Return declared external Python package requirements for isolated uv execution."""
        return list(self.python_dependencies)

    @property
    def warp(self):
        """Universal Pub/Sub sensory and event bus."""
        return warp

    @property
    def tapestry(self):
        """Universal live state & sensory blackboard."""
        return sensory_tapestry

    def publish_event(self, topic: Any, data: Any = None) -> None:
        """Publish a real-time streaming event to Warp."""
        self.warp.publish(topic, data)

    def stitch(self, level: str, message: str, data: dict[str, Any] | None = None) -> Any:
        """Stitch a structured notice/alert into the Tapestry sensory blackboard."""
        return self.tapestry.stitch(level=level, source=self.name, message=message, data=data)

    def set_slot(self, key: str, value: Any) -> None:
        """Set a retained domain state slot in the Tapestry blackboard."""
        self.tapestry.set_slot(key, value)

    def get_slot(self, key: str, default: Any = None) -> Any:
        """Get a retained domain state slot from the Tapestry blackboard."""
        return self.tapestry.get_slot(key, default)

    def get_dependencies(self) -> list[dict[str, Any]]:
        return getattr(self, "dependencies", [])

    @abstractmethod
    def is_available(self) -> bool:
        return True

    def get_strands(self) -> list[Strand]:
        """Automatically discovers all @strand decorated methods on the class."""
        discovered = []
        for attr_name in dir(self):
            if attr_name.startswith("__"):
                continue
            try:
                attr = getattr(self, attr_name)
            except (AttributeError, TypeError, ValueError, RuntimeError) as e:
                logger.debug(f"Error inspecting attribute '{attr_name}' for strands: {e}")
                continue
            if callable(attr) and getattr(attr, "_is_strand", False):
                discovered.append(self._method_to_strand(attr))
        return discovered

    def get_wefts(self) -> list[Weft]:
        """Automatically discovers all @weft decorated methods on the class."""
        discovered = []
        for attr_name in dir(self):
            if attr_name.startswith("__"):
                continue
            try:
                attr = getattr(self, attr_name)
            except (AttributeError, TypeError, ValueError, RuntimeError) as e:
                logger.debug(f"Error inspecting attribute '{attr_name}' for wefts: {e}")
                continue
            if callable(attr) and getattr(attr, "_is_weft", False):
                discovered.append(self._method_to_weft(attr))
        return discovered

    def _method_to_weft(self, method: Callable) -> Weft:
        sig = inspect.signature(method)
        weft_name = getattr(method, "_weft_name", method.__name__)
        weft_pattern = getattr(method, "_weft_pattern")
        weft_desc = getattr(method, "_weft_description", None) or inspect.getdoc(method) or weft_name
        weft_strip = getattr(method, "_weft_strip", True)
        weft_priority = getattr(method, "_weft_priority", 100)

        try:
            hints = get_type_hints(method)
        except (AttributeError, TypeError, NameError, ValueError, KeyError):
            hints = {}

        param_names = [p_name for p_name in sig.parameters if p_name not in ("self", "cls")]
        fields = {}
        for p_name in param_names:
            param = sig.parameters[p_name]
            p_type = hints.get(p_name, Any)
            if param.default is inspect.Parameter.empty:
                fields[p_name] = (p_type, Field(...))
            else:
                fields[p_name] = (p_type, Field(default=param.default))

        args_model = create_model(f"{weft_name}_WeftArgs", **fields) if fields else None

        return Weft(
            name=weft_name,
            pattern=weft_pattern,
            description=weft_desc,
            strip=weft_strip,
            priority=weft_priority,
            handler=method,
            raw_handler=method,
            args_schema=args_model,
            param_names=param_names,
        )

    def _method_to_strand(self, method: Callable) -> Strand:
        sig = inspect.signature(method)
        main_desc, param_docs = _extract_docstring_info(inspect.getdoc(method))
        strand_name = getattr(method, "_strand_name", method.__name__)
        strand_desc = getattr(method, "_strand_description", None) or main_desc or strand_name
        strand_cap = getattr(method, "_strand_capability", None)
        tier_val = _parse_tier(getattr(method, "_strand_tier", CapabilityTier.INTERACT))

        explicit_isolated = getattr(method, "_strand_isolated", None)
        strand_resources = getattr(method, "_strand_resources", None) or getattr(self.manifest, "resources", [])
        if explicit_isolated is not None:
            isolated = bool(explicit_isolated)
        else:
            isolated = bool(
                self.get_python_dependencies()
                or tier_val in (CapabilityTier.PRIVILEGED, CapabilityTier.SYSTEM_EXEC)
                or detects_native_ffi(self)
            )

        timeout = getattr(method, "_strand_timeout", 30.0)
        is_async = inspect.iscoroutinefunction(method)

        try:
            hints = get_type_hints(method)
        except (AttributeError, TypeError, NameError, ValueError, KeyError):
            hints = {}

        fields = {}
        for p_name, param in sig.parameters.items():
            if p_name in ("self", "cls"):
                continue
            p_type = hints.get(p_name, Any)
            p_desc = param_docs.get(p_name, "")
            if param.default is inspect.Parameter.empty:
                fields[p_name] = (p_type, Field(..., description=p_desc))
            else:
                fields[p_name] = (p_type, Field(default=param.default, description=p_desc))

        args_model = create_model(f"{strand_name}_Args", **fields) if fields else None
        schema = (
            args_model.model_json_schema()
            if args_model
            else {"type": "object", "properties": {}, "required": []}
        )
        params, req_list = schema.get("properties", {}), schema.get("required", [])

        invoker = _create_invoker(
            self, method, strand_name, args_model, params, req_list, isolated, is_async, timeout, tier=tier_val
        )

        return Strand(
            name=strand_name,
            description=strand_desc,
            parameters=params,
            required=req_list,
            handler=invoker,
            raw_handler=method,
            capability=strand_cap,
            args_schema=args_model,
            tier=tier_val,
            isolated=isolated,
            resources=strand_resources,
        )

    def build_strand(
        self,
        name: str,
        description: str,
        handler: Callable[[dict[str, Any]], Any],
        args_schema: type[BaseModel] | None = None,
        parameters: dict[str, Any] | None = None,
        required: list[str] | None = None,
        isolated: bool | None = None,
        timeout: float = 30.0,
        capability: str | None = None,
        tier: CapabilityTier | str = CapabilityTier.INTERACT,
        resources: list[str] | None = None,
    ) -> Strand:
        """Helper to build a Strand dynamically."""
        if isinstance(tier, CapabilityTier):
            tier_val = tier
        elif isinstance(tier, str):
            try:
                tier_val = CapabilityTier(tier.lower())
            except ValueError:
                tier_val = CapabilityTier.INTERACT
        else:
            tier_val = CapabilityTier.INTERACT

        if isolated is not None:
            is_isolated = bool(isolated)
        elif (
            self.get_python_dependencies()
            or tier_val in (CapabilityTier.PRIVILEGED, CapabilityTier.SYSTEM_EXEC)
            or detects_native_ffi(self)
        ):
            is_isolated = True
        else:
            is_isolated = False

        schema_model = args_schema or (
            schema_to_model(name, parameters or {}, required or []) if parameters else None
        )
        schema = (
            schema_model.model_json_schema()
            if schema_model
            else {"type": "object", "properties": {}, "required": []}
        )
        params = schema.get("properties", {})
        req_list = schema.get("required", []) if schema_model else (required or [])
        res_list = resources or getattr(self.manifest, "resources", [])

        def _safe_handler(args: dict[str, Any]) -> str:
            val_err, coerced = validate_strand_arguments(
                name, args, schema_model=schema_model, parameters=params, required=req_list
            )
            if val_err:
                return val_err
            if is_isolated:
                return self._run_isolated(name, coerced, timeout=timeout, tier=tier_val)
            try:
                res = handler(coerced)
                return str(res) if res is not None else "ok"
            except (AttributeError, TypeError, ValueError, KeyError, OSError, RuntimeError) as e:
                return f"Error executing strand '{name}': {e}"

        return Strand(
            name=name,
            description=description,
            parameters=params,
            required=req_list,
            handler=_safe_handler,
            raw_handler=handler,
            capability=capability,
            args_schema=schema_model,
            tier=tier_val,
            isolated=is_isolated,
            resources=res_list,
        )

    def _run_isolated(
        self,
        strand_name: str,
        args: dict[str, Any],
        timeout: float = 30.0,
        tier: CapabilityTier | str = CapabilityTier.INTERACT,
    ) -> str:
        """Run strand in an isolated ephemeral subprocess using `uv`."""
        uv_bin = shutil.which("uv")
        if not uv_bin:
            return f"Error: `uv` binary required for isolated strand '{strand_name}' execution."

        tier_str = tier.value if isinstance(tier, CapabilityTier) else str(tier)
        cmd = [uv_bin, "run", "--quiet"]
        for dep in self.get_python_dependencies():
            cmd.extend(["--with", str(dep)])
        cmd.extend([
            "-m",
            "textile.core.isolated_runner",
            self.__class__.__module__,
            self.__class__.__name__,
            strand_name,
            json.dumps(args),
            tier_str,
        ])
        env = dict(os.environ)
        python_path = env.get("PYTHONPATH", "")
        cwd = os.getcwd()
        env["PYTHONPATH"] = f"{cwd}:{python_path}" if python_path else cwd

        if BubblewrapSandbox.is_available() and tier_str.upper() != "PRIVILEGED":
            matching_strand = next((s for s in self.get_strands() if s.name == strand_name), None)
            res_list = matching_strand.resources if matching_strand else getattr(self.manifest, "resources", [])
            cmd = BubblewrapSandbox.wrap_command(cmd, tier=tier_str, workspace_root=cwd, resources=res_list)

        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False, env=env)
            out = res.stdout.strip()
            err = res.stderr.strip()

            if res.returncode == 0 and out:
                try:
                    payload = json.loads(out)
                    if payload.get("success"):
                        res_val = payload.get("result")
                        if isinstance(res_val, (dict, list)):
                            return json.dumps(res_val, indent=2)
                        return str(res_val) if res_val is not None else "ok"
                    return f"Error: {payload.get('error', 'Execution failed')}"
                except (json.JSONDecodeError, ValueError, TypeError):
                    return out

            err_msg = err if err else f"Exit code {res.returncode}"
            return f"Error: Strand '{strand_name}' isolated worker process crashed ({err_msg}). Host process preserved."
        except subprocess.TimeoutExpired:
            return f"Error: Strand '{strand_name}' isolated worker process timed out after {timeout} seconds."
        except (subprocess.SubprocessError, OSError, ValueError) as e:
            return f"Error executing isolated strand '{strand_name}': {e}"

    def _execute_direct(self, strand_name: str, args: dict[str, Any]) -> str:
        for s in self.get_strands():
            if s.name == strand_name:
                if s.raw_handler is not None:
                    raw_h: Any = s.raw_handler
                    try:
                        res = raw_h(**args)
                    except TypeError:
                        res = raw_h(args)
                elif s.handler is not None:
                    res = s.handler(args)
                else:
                    return "ok"

                if isinstance(res, (dict, list)):
                    return json.dumps(res, indent=2)
                return str(res) if res is not None else "ok"
        return f"Error: Strand '{strand_name}' not implemented in yarn '{self.name}'."

    def execute_sync(self, strand_name: str, args: dict[str, Any]) -> str:
        for s in self.get_strands():
            if s.name == strand_name and s.handler is not None:
                return s.handler(args)
        return f"Error: Strand '{strand_name}' not implemented in yarn '{self.name}'."

    def on_load(self) -> None: pass
    def on_unload(self) -> None: pass
    def start_event_stream(self, publish_cb: Callable[[str], None], stop_event: Any) -> None: pass
