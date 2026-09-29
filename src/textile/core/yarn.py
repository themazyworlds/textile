"""
Textile Core Yarn Abstract Base Class & Execution Engine.
"""

import inspect
import json
import logging
import os
import shutil
import subprocess
import sys
from abc import ABC
from collections.abc import Callable
from pathlib import Path
from typing import Any, get_type_hints

from pydantic import BaseModel, Field, create_model

from textile.core.decorators import _parse_tier
from textile.core.elastic import EventUrgency, elastic
from textile.core.errors import TextileError
from textile.core.manifest import YarnManifest
from textile.core.sandbox import BubblewrapSandbox
from textile.core.strands import CapabilityTier, Strand, Weft
from textile.core.tapestry import sensory_tapestry
from textile.core.validation import (
    _extract_docstring_info,
    detects_native_ffi,
    schema_to_model,
    validate_strand_arguments,
)

logger = logging.getLogger(__name__)

STRAND_EXEC_ERRORS = (
    TextileError,
    AttributeError,
    TypeError,
    ValueError,
    KeyError,
    OSError,
    RuntimeError,
    json.JSONDecodeError,
)


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
        return _exec_sync_strand(yarn, method, strand_name, args, args_model, params, req_list, isolated, timeout, tier)

    return _sync_invoker


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

    def get_python_dependencies(self) -> list[str]:
        """Return declared external Python package requirements for isolated uv execution."""
        return list(self.python_dependencies)

    @property
    def elastic(self):
        """Universal cross-process event and sensory bus."""
        return elastic

    @property
    def tapestry(self):
        """Universal live state & sensory blackboard."""
        return sensory_tapestry

    def publish_event(
        self,
        topic: str,
        data: Any = None,
        summary: str = "",
        urgency: EventUrgency = EventUrgency.NOTICE,
        retained_slot: str | None = None,
        retained_value: Any = None,
    ) -> None:
        """Publish a real-time event to Elastic."""
        self.elastic.broadcast(
            topic=str(topic),
            source=self.name,
            summary=summary or f"Event '{topic}' from yarn '{self.name}'",
            urgency=urgency,
            data=data if isinstance(data, dict) else {"payload": data},
            retained_slot=retained_slot,
            retained_value=retained_value,
        )

    def stitch(self, level: str, message: str, data: dict[str, Any] | None = None) -> Any:
        """Stitch a structured notice/alert into the Tapestry sensory blackboard."""
        return self.tapestry.stitch(level=level, source=self.name, message=message, data=data)

    def set_slot(self, key: str, value: Any) -> None:
        """Set a retained domain state slot in Elastic and Tapestry."""
        self.elastic.occupy_seat(key, value, source=self.name)

    def get_slot(self, key: str, default: Any = None) -> Any:
        """Get a retained domain state slot from Elastic."""
        return self.elastic.get_seat(key, default)

    def get_dependencies(self) -> list[dict[str, Any]]:
        return getattr(self, "dependencies", [])

    def is_available(self) -> bool:
        """Check if runtime dependencies and environment are met. Defaults to True."""
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
        tier_val = _parse_tier(getattr(method, "_strand_tier", CapabilityTier.INTERACT), strand_name)

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
        schema = args_model.model_json_schema() if args_model else {"type": "object", "properties": {}, "required": []}
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
        tier_val = _parse_tier(tier, name)

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

        schema_model = args_schema or (schema_to_model(name, parameters or {}, required or []) if parameters else None)
        schema = (
            schema_model.model_json_schema() if schema_model else {"type": "object", "properties": {}, "required": []}
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
        cmd = [uv_bin, "run", "--no-project", "--no-sync", "--quiet"]
        for dep in self.get_python_dependencies():
            cmd.extend(["--with", str(dep)])
        cmd.extend(
            [
                "-m",
                "textile.core.isolated_runner",
                self.__class__.__module__,
                self.__class__.__name__,
                strand_name,
                json.dumps(args),
                tier_str,
            ]
        )
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

    def on_load(self) -> None:
        pass

    def on_unload(self) -> None:
        pass
