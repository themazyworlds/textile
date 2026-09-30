"""
Textile Core Yarn Abstract Base Class & Execution Engine.
"""

import inspect
import logging
import sys
from abc import ABC
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from textile.core.contracts.manifest import YarnManifest
from textile.core.execution.decorators import _parse_tier
from textile.core.execution.invoker import (
    InvokerConfig,
    _build_args_model,
    _create_invoker,
    _format_handler_result,
)
from textile.core.execution.isolated_runner import execute_isolated_strand
from textile.core.execution.strands import CapabilityTier, Strand, Weft
from textile.core.execution.validation import (
    _extract_docstring_info,
    detects_native_ffi,
    schema_to_model,
    validate_strand_arguments,
)
from textile.core.telemetry.elastic import EventUrgency, elastic
from textile.core.telemetry.tapestry import sensory_tapestry

logger = logging.getLogger(__name__)


@dataclass
class StrandConfig:
    args_schema: type[BaseModel] | None = None
    parameters: dict[str, Any] | None = None
    required: list[str] | None = None
    isolated: bool | None = None
    timeout: float = 30.0
    capability: str | None = None
    tier: CapabilityTier | str = CapabilityTier.INTERACT
    resources: list[str] | None = None


@dataclass
class EventOptions:
    data: Any = None
    summary: str = ""
    urgency: EventUrgency = EventUrgency.NOTICE
    retained_slot: str | None = None
    retained_value: Any = None


class Yarn(ABC):
    """Abstract Base Class for all Textile Capability Yarns."""

    manifest: YarnManifest

    def __init__(self, manifest: YarnManifest | None = None) -> None:
        if manifest is not None:
            self.manifest = manifest
            return

        if mod_file := getattr(
            sys.modules.get(self.__class__.__module__), "__file__", None
        ):
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

    def __getattr__(self, name: str) -> Any:
        manifest = self.__dict__.get("manifest")
        if manifest is not None and hasattr(manifest, name):
            return getattr(manifest, name)
        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")

    def __setattr__(self, name: str, value: Any) -> None:
        manifest = self.__dict__.get("manifest")
        if name != "manifest" and manifest is not None and hasattr(manifest, name):
            setattr(manifest, name, value)
        else:
            super().__setattr__(name, value)

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
        options: EventOptions | None = None,
        **kwargs: Any,
    ) -> None:
        """Publish a real-time event to Elastic."""
        opts = options or EventOptions(**kwargs)
        self.elastic.broadcast(
            topic=topic,
            source=self.name,
            summary=opts.summary or f"Event '{topic}' from yarn '{self.name}'",
            urgency=opts.urgency,
            data=(
                opts.data
                if isinstance(opts.data, dict)
                else {"payload": opts.data}
            ),
            retained_slot=opts.retained_slot,
            retained_value=opts.retained_value,
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
        """Return system dependency manifests declared for this yarn."""
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
        """Convert a @weft decorated method into a Weft instance."""
        sig = inspect.signature(method)
        weft_name = getattr(method, "_weft_name", method.__name__)
        weft_pattern = getattr(method, "_weft_pattern")
        weft_desc = getattr(method, "_weft_description", None) or inspect.getdoc(method) or weft_name
        weft_strip = getattr(method, "_weft_strip", True)
        weft_priority = getattr(method, "_weft_priority", 100)

        param_names = [p_name for p_name in sig.parameters if p_name not in ("self", "cls")]
        args_model = _build_args_model(method, f"{weft_name}_WeftArgs")

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

    def _determine_isolation(self, explicit_isolated: bool | None, tier_val: CapabilityTier) -> bool:
        """Determine whether a strand requires process isolation based on explicit config or system tier."""
        if explicit_isolated is not None:
            return bool(explicit_isolated)
        return bool(
            self.get_python_dependencies()
            or tier_val in (CapabilityTier.PRIVILEGED, CapabilityTier.SYSTEM_EXEC)
            or detects_native_ffi(self)
        )

    def _method_to_strand(self, method: Callable) -> Strand:
        """Convert a @strand decorated method into a Strand instance."""
        main_desc, param_docs = _extract_docstring_info(inspect.getdoc(method))
        strand_name = getattr(method, "_strand_name", method.__name__)
        strand_desc = getattr(method, "_strand_description", None) or main_desc or strand_name
        strand_cap = getattr(method, "_strand_capability", None)
        tier_val = _parse_tier(getattr(method, "_strand_tier", CapabilityTier.INTERACT), strand_name)

        explicit_isolated = getattr(method, "_strand_isolated", None)
        strand_resources = getattr(method, "_strand_resources", None) or getattr(self.manifest, "resources", [])
        isolated = self._determine_isolation(explicit_isolated, tier_val)

        timeout = getattr(method, "_strand_timeout", 30.0)
        is_async = inspect.iscoroutinefunction(method)

        args_model = _build_args_model(method, f"{strand_name}_Args", param_docs)
        schema = args_model.model_json_schema() if args_model else {"type": "object", "properties": {}, "required": []}
        params, req_list = schema.get("properties", {}), schema.get("required", [])

        invoker = _create_invoker(
            self,
            method,
            strand_name,
            InvokerConfig(
                args_model=args_model,
                params=params,
                req_list=req_list,
                isolated=isolated,
                is_async=is_async,
                timeout=timeout,
                tier=tier_val,
            ),
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
        config: StrandConfig | None = None,
        **kwargs: Any,
    ) -> Strand:
        """Helper to build a Strand dynamically."""
        cfg = config or StrandConfig(**kwargs)
        tier_val = _parse_tier(cfg.tier, name)
        is_isolated = self._determine_isolation(cfg.isolated, tier_val)

        schema_model = cfg.args_schema or (
            schema_to_model(name, cfg.parameters or {}, cfg.required or []) if cfg.parameters else None
        )
        schema = (
            schema_model.model_json_schema() if schema_model else {"type": "object", "properties": {}, "required": []}
        )
        params = schema.get("properties", {})
        req_list = schema.get("required", []) if schema_model else (cfg.required or [])
        res_list = cfg.resources or getattr(self.manifest, "resources", [])

        def _safe_handler(args: dict[str, Any]) -> str:
            val_err, coerced = validate_strand_arguments(
                name, args, schema_model=schema_model, parameters=params, required=req_list
            )
            if val_err:
                return val_err
            if is_isolated:
                return self._run_isolated(name, coerced, timeout=cfg.timeout, tier=tier_val)
            try:
                res = handler(coerced)
                return _format_handler_result(res)
            except (AttributeError, TypeError, ValueError, KeyError, OSError, RuntimeError) as e:
                return f"Error executing strand '{name}': {e}"

        return Strand(
            name=name,
            description=description,
            parameters=params,
            required=req_list,
            handler=_safe_handler,
            raw_handler=handler,
            capability=cfg.capability,
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
        return execute_isolated_strand(self, strand_name, args, timeout=timeout, tier=tier)

    def _execute_direct(self, strand_name: str, args: dict[str, Any]) -> str:
        """Execute strand raw handler or bound handler directly without validation or isolation wrapper."""
        strand = next((s for s in self.get_strands() if s.name == strand_name), None)
        if strand is None:
            return f"Error: Strand '{strand_name}' not implemented in yarn '{self.name}'."

        if strand.raw_handler is not None:
            raw_h: Any = strand.raw_handler
            sig = inspect.signature(raw_h)
            try:
                bound = sig.bind(**args)
                res = raw_h(*bound.args, **bound.kwargs)
            except TypeError:
                res = raw_h(args)
        elif strand.handler is not None:
            res = strand.handler(args)
        else:
            return "ok"

        return _format_handler_result(res)

    def execute_sync(self, strand_name: str, args: dict[str, Any]) -> str:
        """Execute strand synchronously by matching name in discovered strands."""
        return next(
            (
                s.handler(args)
                for s in self.get_strands()
                if s.name == strand_name and s.handler is not None
            ),
            f"Error: Strand '{strand_name}' not implemented in yarn '{self.name}'.",
        )

    def on_load(self) -> None:
        """Lifecycle hook invoked when the yarn is initialized and loaded into Loom."""

    def on_unload(self) -> None:
        """Lifecycle hook invoked when the yarn is unloaded from Loom."""
