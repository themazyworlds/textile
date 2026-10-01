"""
Textile Strand & Weft Reflection, Factory, and Execution Directives.
Converts @strand and @weft decorated methods on Yarn instances into Strand and Weft objects.
"""

import asyncio
import inspect
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from textile.core.definitions.errors import SAFE_EXCEPTIONS
from textile.core.execution.decorators import _parse_tier
from textile.core.execution.invoker import (
    InvokerConfig,
    _build_args_model,
    _create_invoker,
    _format_handler_result,
    execute_direct,
)
from textile.core.execution.isolated_runner import execute_isolated_strand
from textile.core.execution.strands import CapabilityTier, Strand, Weft
from textile.core.execution.validation import (
    _extract_docstring_info,
    detects_native_ffi,
    schema_to_model,
    validate_strand_arguments,
)
from textile.core.telemetry.log import get_logger

logger = get_logger(__name__)


@dataclass(slots=True)
class StrandConfig:
    args_schema: type[BaseModel] | None = None
    parameters: dict[str, Any] | None = None
    required: list[str] | None = None
    isolated: bool | None = None
    timeout: float = 30.0
    capability: str | None = None
    tier: CapabilityTier | str = CapabilityTier.INTERACT
    resources: list[str] | None = None


__all__ = [
    "StrandConfig",
    "build_dynamic_strand",
    "determine_isolation",
    "execute_direct",
    "method_to_strand",
    "method_to_weft",
    "reflect_strands",
    "reflect_wefts",
]


def determine_isolation(yarn: Any, explicit_isolated: bool | None, tier_val: CapabilityTier) -> bool:
    """Determine whether a strand requires process isolation based on explicit config or system tier."""
    if explicit_isolated is not None:
        return bool(explicit_isolated)
    deps = getattr(yarn, "get_python_dependencies", lambda: [])()
    return bool(
        deps
        or tier_val in (CapabilityTier.PRIVILEGED, CapabilityTier.SYSTEM_EXEC)
        or detects_native_ffi(yarn)
    )


def method_to_weft(yarn: Any, method: Callable[..., Any]) -> Weft:
    """Convert a @weft decorated method into a Weft instance."""
    sig = inspect.signature(method)
    weft_name = getattr(method, "_weft_name", method.__name__)
    weft_pattern = getattr(method, "_weft_pattern")
    weft_desc = getattr(method, "_weft_description", None) or inspect.getdoc(method) or weft_name
    weft_strip = getattr(method, "_weft_strip", True)
    weft_priority = getattr(method, "_weft_priority", 100)

    param_names = [p_name for p_name in sig.parameters if p_name not in ("self", "cls")]
    args_model = _build_args_model(method, f"{weft_name}_WeftArgs", is_strand=False)

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


def method_to_strand(yarn: Any, method: Callable[..., Any]) -> Strand:
    """Convert a @strand decorated method into a Strand instance."""
    main_desc, param_docs = _extract_docstring_info(inspect.getdoc(method))
    strand_name = getattr(method, "_strand_name", method.__name__)
    strand_desc = getattr(method, "_strand_description", None) or main_desc or strand_name
    strand_cap = getattr(method, "_strand_capability", None)
    tier_val = _parse_tier(getattr(method, "_strand_tier", CapabilityTier.INTERACT), strand_name)

    manifest_res = getattr(getattr(yarn, "manifest", None), "resources", [])
    explicit_isolated = getattr(method, "_strand_isolated", None)
    strand_resources = getattr(method, "_strand_resources", None) or manifest_res
    isolated = determine_isolation(yarn, explicit_isolated, tier_val)

    timeout = getattr(method, "_strand_timeout", 30.0)

    args_model = _build_args_model(method, f"{strand_name}_Args", param_docs)
    schema = args_model.model_json_schema() if args_model else {"type": "object", "properties": {}, "required": []}
    params, req_list = schema.get("properties", {}), schema.get("required", [])

    invoker = _create_invoker(
        yarn,
        method,
        strand_name,
        InvokerConfig(
            args_model=args_model,
            params=params,
            req_list=req_list,
            isolated=isolated,
            timeout=timeout,
            tier=tier_val,
        ),
        isolated_runner=execute_isolated_strand,
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


def reflect_strands(yarn: Any) -> list[Strand]:
    """Inspect class-level attributes on yarn to discover @strand decorated methods."""
    discovered = []
    cls = type(yarn)
    for attr_name in dir(cls):
        if attr_name.startswith("__"):
            continue
        try:
            unbound = getattr(cls, attr_name, None)
        except SAFE_EXCEPTIONS as e:
            logger.debug("strand.reflection_attribute_error", attribute=attr_name, error=str(e))
            continue
        if callable(unbound) and getattr(unbound, "_is_strand", False):
            bound = getattr(yarn, attr_name)
            discovered.append(method_to_strand(yarn, bound))
    return discovered


def reflect_wefts(yarn: Any) -> list[Weft]:
    """Inspect class-level attributes on yarn to discover @weft decorated methods."""
    discovered = []
    cls = type(yarn)
    for attr_name in dir(cls):
        if attr_name.startswith("__"):
            continue
        try:
            unbound = getattr(cls, attr_name, None)
        except SAFE_EXCEPTIONS as e:
            logger.debug("weft.reflection_attribute_error", attribute=attr_name, error=str(e))
            continue
        if callable(unbound) and getattr(unbound, "_is_weft", False):
            bound = getattr(yarn, attr_name)
            discovered.append(method_to_weft(yarn, bound))
    return discovered


def build_dynamic_strand(
    yarn: Any,
    name: str,
    description: str,
    handler: Callable[[dict[str, Any]], Any],
    config: StrandConfig | None = None,
    **kwargs: Any,
) -> Strand:
    """Dynamically construct a Strand instance."""
    cfg = config or StrandConfig(**kwargs)
    tier_val = _parse_tier(cfg.tier, name)
    is_isolated = determine_isolation(yarn, cfg.isolated, tier_val)

    schema_model: type[BaseModel] | None = cfg.args_schema or (
        schema_to_model(name, cfg.parameters or {}, cfg.required or []) if cfg.parameters else None
    )
    schema = (
        schema_model.model_json_schema() if schema_model else {"type": "object", "properties": {}, "required": []}
    )
    params = schema.get("properties", {})
    req_list = schema.get("required", []) if schema_model else (cfg.required or [])
    manifest_res = getattr(getattr(yarn, "manifest", None), "resources", [])
    res_list = cfg.resources or manifest_res

    async def _safe_handler(args: dict[str, Any]) -> str:
        val_err, coerced = validate_strand_arguments(
            name, args, schema_model=schema_model, parameters=params, required=req_list
        )
        if val_err:
            return val_err
        if is_isolated:
            return await asyncio.to_thread(
                execute_isolated_strand, yarn, name, coerced, timeout=cfg.timeout, tier=tier_val
            )
        try:
            if inspect.iscoroutinefunction(handler):
                res = await handler(coerced)
            else:
                res = await asyncio.to_thread(handler, coerced)
            return _format_handler_result(res)
        except SAFE_EXCEPTIONS as e:
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
