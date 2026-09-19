"""
Textile Core Yarn & Strand System - Base Interfaces & Definitions.
"""

import inspect
import json
import logging
import multiprocessing
import os
import pwd
import re
import shutil
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Literal, Optional, Tuple, Type, Union

from pydantic import BaseModel, Field, ValidationError, create_model

logger = logging.getLogger(__name__)

# Standard Layer Tiers (Higher number = outer layer with higher override authority)
LAYER_BASE = 10                # Base OS / Pure POSIX kernel fallbacks
LAYER_DESKTOP_PROTOCOL = 50   # Generic Wayland, XDG, D-Bus protocols
LAYER_COMPOSITOR_DE = 100     # Specific Compositors & DEs (Hyprland, Caelestia, GNOME, KDE)
LAYER_SESSION_MANAGER = 150   # Session Managers & Cgroup Wrappers (UWSM, systemd-run)
LAYER_USER_OVERRIDE = 1000    # User custom overrides (~/.config/textile/yarns/)


def resolve_terminal_and_shell() -> Tuple[str, str]:
    term = os.environ.get("TERM", "xterm-256color")
    shell_path = pwd.getpwuid(os.getuid()).pw_shell
    if not (os.path.isfile(shell_path) and os.access(shell_path, os.X_OK)):
        raise RuntimeError("Shell binary not accessible on disk.")
    return term, shell_path


def schema_to_model(strand_name: str, parameters: Dict[str, Any], required: List[str]) -> Type[BaseModel]:
    """Dynamically synthesize a Pydantic BaseModel from JSON schema parameters."""
    fields: Dict[str, Any] = {}
    type_map = {"string": str, "integer": int, "number": float, "boolean": bool, "array": list, "object": dict}
    for p_name, p_spec in (parameters or {}).items():
        desc = p_spec.get("description", "")
        enum_vals = p_spec.get("enum")
        field_type = Literal[tuple(enum_vals)] if enum_vals else type_map.get(str(p_spec.get("type", "string")).lower(), Any)  # type: ignore
        if p_name in (required or []):
            fields[p_name] = (field_type, Field(..., description=desc))
        else:
            fields[p_name] = (Optional[field_type], Field(default=None, description=desc))
    return create_model(f"{strand_name}_Args", **fields)


@dataclass
class Strand:
    """Represents a single callable tool/strand exposed by a yarn."""

    name: str
    description: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    handler: Optional[Callable[[Dict[str, Any]], str]] = None
    required: List[str] = field(default_factory=list)
    raw_handler: Optional[Callable[[Dict[str, Any]], Any]] = None
    capability: Optional[str] = None
    args_schema: Optional[Type[BaseModel]] = None

    def to_mcp_definition(self) -> Dict[str, Any]:
        """Convert strand schema into Model Context Protocol format."""
        if self.args_schema:
            return {
                "name": self.name,
                "description": self.description,
                "inputSchema": self.args_schema.model_json_schema(),
            }
        return {
            "name": self.name,
            "description": self.description,
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
    handler: Optional[Callable[..., Any]] = None
    raw_handler: Optional[Callable[..., Any]] = None
    args_schema: Optional[Type[BaseModel]] = None
    param_names: List[str] = field(default_factory=list)

    def execute_match(self, match: re.Match) -> Any:
        """Execute weft attunement handler with regex match extracted arguments coerced with Pydantic."""
        raw_kwargs: Dict[str, Any] = {}
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


def _isolated_worker(module_name: str, class_name: str, strand_name: str, args: Dict[str, Any], conn: Any) -> None:
    try:
        import importlib
        mod = importlib.import_module(module_name)
        yarn = getattr(mod, class_name)()
        res = yarn._execute_direct(strand_name, args)
        conn.send((True, str(res) if res is not None else "ok"))
    except Exception as e:
        conn.send((False, f"Error: {e}"))
    finally:
        try:
            conn.close()
        except Exception:
            pass


def validate_strand_schema(strand_name: str, parameters: Any, required: Any) -> List[str]:
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
    args: Dict[str, Any],
    schema_model: Optional[Type[BaseModel]] = None,
    parameters: Optional[Dict[str, Any]] = None,
    required: Optional[List[str]] = None,
) -> Tuple[Optional[str], Dict[str, Any]]:
    """Strictly validates arguments using Pydantic v2."""
    if not schema_model:
        if parameters:
            try:
                schema_model = schema_to_model(strand_name, parameters, required or [])
            except Exception:
                return None, args
        else:
            return None, args

    clean_args = dict(args or {})
    if required:
        for r in required:
            if r in clean_args and isinstance(clean_args[r], str) and not clean_args[r].strip():
                p_type = (parameters or {}).get(r, {}).get("type", "value")
                return f"Validation Hint: Strand '{strand_name}' expected required parameter '{r}' (type: {p_type}), but it went missing in action!", args

    try:
        validated = schema_model.model_validate(clean_args)
        return None, {k: v for k, v in validated.model_dump().items() if v is not None}
    except ValidationError as e:
        err = e.errors()[0]
        loc = str(err["loc"][0]) if err["loc"] else "parameter"
        err_type = err["type"]
        if "missing" in err_type:
            p_type = (parameters or {}).get(loc, {}).get("type", "value")
            return f"Validation Hint: Strand '{strand_name}' expected required parameter '{loc}' (type: {p_type}), but it went missing in action!", args
        if "literal" in err_type or "enum" in err_type:
            expected = err.get("ctx", {}).get("expected", "")
            return f"Validation Hint: Invalid action/option '{args.get(loc)}' for strand '{strand_name}'. Available options: [{expected}]", args
        return f"Validation Hint: Strand '{strand_name}' parameter '{loc}' validation failed: {err['msg']}.", args


def _extract_docstring_info(doc: Optional[str]) -> Tuple[str, Dict[str, str]]:
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
    func: Optional[Callable] = None,
    *,
    name: Optional[str] = None,
    description: Optional[str] = None,
    capability: Optional[str] = None,
    isolated: bool = False,
    timeout: float = 30.0,
):
    """Decorator marking a BaseYarn method as an executable Desktop Strand."""
    def decorator(fn: Callable) -> Callable:
        fn._is_strand = True
        fn._strand_name = name or fn.__name__
        fn._strand_description = description
        fn._strand_capability = capability
        fn._strand_isolated = isolated
        fn._strand_timeout = timeout
        return fn

    return decorator(func) if func is not None else decorator


def weft(
    func: Optional[Callable] = None,
    *,
    pattern: Union[str, re.Pattern],
    name: Optional[str] = None,
    description: Optional[str] = None,
    strip: bool = True,
    priority: int = 100,
):
    """Decorator marking a BaseYarn method as a real-time streaming token Weft attunement."""
    compiled_pattern = re.compile(pattern) if isinstance(pattern, str) else pattern

    def decorator(fn: Callable) -> Callable:
        fn._is_weft = True
        fn._weft_name = name or fn.__name__
        fn._weft_pattern = compiled_pattern
        fn._weft_description = description
        fn._weft_strip = strip
        fn._weft_priority = priority
        return fn

    return decorator(func) if func is not None else decorator


class BaseYarn(ABC):
    """Abstract Base Class for all Textile Capability Yarns."""

    publisher: str = ""
    name: str = "base_yarn"
    description: str = "Base Yarn"
    version: str = "1.0.0"
    layer: int = LAYER_BASE
    dependencies: List[Dict[str, Any]] = []

    @property
    def warp(self):
        """Universal Pub/Sub sensory and event bus."""
        from textile.core.warp import warp
        return warp

    @property
    def tapestry(self):
        """Universal live state & sensory blackboard."""
        from textile.core.tapestry import tapestry
        return tapestry

    def publish_event(self, topic: Any, data: Any = None) -> None:
        """Publish a real-time streaming event to Warp."""
        self.warp.publish(topic, data)

    def stitch(self, level: str, message: str, data: Optional[Dict[str, Any]] = None) -> Any:
        """Stitch a structured notice/alert into the Tapestry sensory blackboard."""
        return self.tapestry.stitch(level=level, source=self.name, message=message, data=data)

    def bind(self, level: str, message: str, data: Optional[Dict[str, Any]] = None) -> Any:
        """Alias for stitch()."""
        return self.stitch(level=level, message=message, data=data)

    def set_slot(self, key: str, value: Any) -> None:
        """Set a retained domain state slot in the Tapestry blackboard."""
        self.tapestry.set_slot(key, value)

    def get_slot(self, key: str, default: Any = None) -> Any:
        """Get a retained domain state slot from the Tapestry blackboard."""
        return self.tapestry.get_slot(key, default)

    def get_dependencies(self) -> List[Dict[str, Any]]:
        return getattr(self, "dependencies", [])

    @abstractmethod
    def is_available(self) -> bool:
        return True

    def get_strands(self) -> List[Strand]:
        """Automatically discovers all @strand decorated methods on the class."""
        discovered = []
        for attr_name in dir(self):
            if attr_name.startswith("__"):
                continue
            try:
                attr = getattr(self, attr_name)
            except Exception:
                continue
            if callable(attr) and getattr(attr, "_is_strand", False):
                discovered.append(self._method_to_strand(attr))
        return discovered

    def get_wefts(self) -> List[Weft]:
        """Automatically discovers all @weft decorated methods on the class."""
        discovered = []
        for attr_name in dir(self):
            if attr_name.startswith("__"):
                continue
            try:
                attr = getattr(self, attr_name)
            except Exception:
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
            from typing import get_type_hints
            hints = get_type_hints(method)
        except Exception:
            hints = {}

        param_names = [p_name for p_name in sig.parameters.keys() if p_name not in ("self", "cls")]
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
        isolated = getattr(method, "_strand_isolated", False)
        timeout = getattr(method, "_strand_timeout", 30.0)
        is_async = inspect.iscoroutinefunction(method)

        try:
            from typing import get_type_hints
            hints = get_type_hints(method)
        except Exception:
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
        schema = args_model.model_json_schema() if args_model else {"type": "object", "properties": {}, "required": []}
        params, req_list = schema.get("properties", {}), schema.get("required", [])

        if is_async:
            async def _async_invoker(args: Dict[str, Any]) -> str:
                val_err, coerced = validate_strand_arguments(strand_name, args, schema_model=args_model, parameters=params, required=req_list)
                if val_err:
                    return val_err
                try:
                    res = await method(**coerced)
                    return json.dumps(res, indent=2) if isinstance(res, (dict, list)) else (str(res) if res is not None else "ok")
                except Exception as e:
                    return f"Error executing strand '{strand_name}': {e}"
            invoker = _async_invoker
        else:
            def _sync_invoker(args: Dict[str, Any]) -> str:
                val_err, coerced = validate_strand_arguments(strand_name, args, schema_model=args_model, parameters=params, required=req_list)
                if val_err:
                    return val_err
                if isolated:
                    return self._run_isolated(strand_name, coerced, timeout=timeout)
                try:
                    res = method(**coerced)
                    return json.dumps(res, indent=2) if isinstance(res, (dict, list)) else (str(res) if res is not None else "ok")
                except Exception as e:
                    return f"Error executing strand '{strand_name}': {e}"
            invoker = _sync_invoker

        return Strand(
            name=strand_name,
            description=strand_desc,
            parameters=params,
            required=req_list,
            handler=invoker,
            raw_handler=method,
            capability=strand_cap,
            args_schema=args_model,
        )

    def build_strand(
        self,
        name: str,
        description: str,
        handler: Callable[[Dict[str, Any]], Any],
        args_schema: Optional[Type[BaseModel]] = None,
        parameters: Optional[Dict[str, Any]] = None,
        required: Optional[List[str]] = None,
        isolated: bool = False,
        timeout: float = 30.0,
        capability: Optional[str] = None,
    ) -> Strand:
        """Helper to build a Strand dynamically."""
        schema_model = args_schema or (schema_to_model(name, parameters or {}, required or []) if parameters else None)
        schema = schema_model.model_json_schema() if schema_model else {"type": "object", "properties": {}, "required": []}
        params, req_list = (schema.get("properties", {}), schema.get("required", [])) if schema_model else (parameters or {}, required or [])

        def _safe_handler(args: Dict[str, Any]) -> str:
            val_err, coerced = validate_strand_arguments(name, args, schema_model=schema_model, parameters=params, required=req_list)
            if val_err:
                return val_err
            if isolated:
                return self._run_isolated(name, coerced, timeout=timeout)
            try:
                res = handler(coerced)
                return str(res) if res is not None else "ok"
            except Exception as e:
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
        )

    def _run_isolated(self, strand_name: str, args: Dict[str, Any], timeout: float = 30.0) -> str:
        ctx = multiprocessing.get_context("spawn")
        p_conn, c_conn = ctx.Pipe()
        proc = ctx.Process(target=_isolated_worker, args=(self.__class__.__module__, self.__class__.__name__, strand_name, args, c_conn))
        proc.start()
        c_conn.close()

        got_result, result = False, None
        try:
            if p_conn.poll(timeout):
                try:
                    _, result = p_conn.recv()
                    got_result = True
                except EOFError:
                    pass
        finally:
            try:
                p_conn.close()
            except Exception:
                pass

        proc.join(timeout=1.0)
        if proc.is_alive():
            proc.kill()
            proc.join(timeout=1.0)

        if got_result:
            return result or "ok"
        if proc.exitcode is not None and proc.exitcode != 0:
            return f"Error: Strand '{strand_name}' isolated worker process crashed (exit code {proc.exitcode}). Host process preserved."
        return f"Error: Strand '{strand_name}' isolated worker process timed out after {timeout} seconds."

    def _execute_direct(self, strand_name: str, args: Dict[str, Any]) -> str:
        for s in self.get_strands():
            if s.name == strand_name:
                h = s.raw_handler or s.handler
                return h(args) if h else "ok"
        return f"Error: Strand '{strand_name}' not implemented in yarn '{self.name}'."

    def execute_strand(self, strand_name: str, args: Dict[str, Any]) -> str:
        for s in self.get_strands():
            if s.name == strand_name and s.handler is not None:
                return s.handler(args)
        return f"Error: Strand '{strand_name}' not implemented in yarn '{self.name}'."

    def on_load(self) -> None: pass
    def on_unload(self) -> None: pass
    def start_event_stream(self, publish_cb: Callable[[str], None], stop_event: Any) -> None: pass

