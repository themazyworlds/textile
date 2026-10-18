"""
Textile Strand Reflection, Factory, and Execution Directives.
Converts @strand decorated methods on Yarn instances into Strand objects.
"""

import inspect
from collections.abc import Callable
from typing import Any, cast

from needle import CapabilityTier, Strand
from needle import parse_capability_tier as _parse_tier
from needle.errors import SAFE_EXCEPTIONS

from textile.core.execution.invoker import (
    InvokerConfig,
    _create_invoker,
    execute_direct,
)
from textile.core.execution.validation import (
    _extract_docstring_info,
)
from textile.core.telemetry.log import get_logger
lazy from textile.core.execution.runner import execute_strand_async

logger = get_logger(__name__)


__all__ = [
    "bind_strand_to_core",
    "execute_direct",
    "method_to_strand",
    "reflect_strands",
]


def method_to_strand(yarn: Any, method: Callable[..., Any]) -> Strand:
    """Convert a @strand decorated method into a Strand instance."""
    main_desc, param_docs = _extract_docstring_info(inspect.getdoc(method))
    strand_name = getattr(method, "_strand_name", method.__name__)
    raw_desc = getattr(method, "_strand_description", None) or main_desc or strand_name
    strand_desc = raw_desc.splitlines()[0].strip() if raw_desc else strand_name
    strand_cap = getattr(method, "_strand_capability", None)
    tier_val = _parse_tier(getattr(method, "_strand_tier", CapabilityTier.INTERACT), strand_name)

    no_timeout = getattr(method, "_strand_no_timeout", False)
    timeout = None if no_timeout else getattr(method, "_strand_timeout", 30.0)

    sig = inspect.signature(method)
    params: dict[str, Any] = {}
    req_list: list[str] = []
    type_map = {str: "string", int: "integer", float: "number", bool: "boolean", list: "array", dict: "object"}
    for p_name, param in sig.parameters.items():
        if p_name in {"self", "cls"}:
            continue
        ann = param.annotation
        p_type = type_map.get(ann, "string") if ann is not inspect.Parameter.empty else "string"
        prop: dict[str, Any] = {"type": p_type}
        if p_desc := param_docs.get(p_name):
            prop["description"] = p_desc
        if param.default is inspect.Parameter.empty:
            req_list.append(p_name)
        else:
            prop["default"] = param.default
        params[p_name] = prop

    params["otp"] = {
        "type": "string",
        "description": "Optional single-use 6-digit 2FA confirmation code displayed on user screen",
    }

    runner = execute_strand_async
    invoker = _create_invoker(
        yarn,
        method,
        strand_name,
        InvokerConfig(
            args_model=None,
            params=params,
            req_list=req_list,
            timeout=timeout,
            tier=tier_val,
        ),
        runner=runner,
    )

    s_reason = getattr(method, "_strand_reason", None)
    s_fallback = getattr(method, "_strand_fallback", None)
    s_resources = getattr(method, "_strand_resources", list(getattr(yarn, "resources", [])))

    return Strand(
        name=strand_name,
        description=strand_desc,
        parameters=params,
        required=req_list,
        handler=invoker,
        raw_handler=method,
        capability=strand_cap,
        args_schema=None,
        tier=tier_val,
        resources=s_resources,
        timeout=timeout,
        no_timeout=no_timeout,
        reason=s_reason,
        fallback=s_fallback,
    )


def bind_strand_to_core(yarn: Any, strand: Strand) -> Strand:
    """Bind a raw SDK or custom strand to Core invoker, runner, and security policies."""
    raw_fn = strand.raw_handler or strand.handler
    if raw_fn is None:
        return strand

    # If raw_fn is an unwrapped method or function, wrap it into a Core invoker
    params = dict(strand.parameters) if strand.parameters else {}
    if "otp" not in params:
        params["otp"] = {
            "type": "string",
            "description": "Optional single-use 6-digit 2FA confirmation code displayed on user screen",
        }

    tier_val = _parse_tier(strand.tier, strand.name)
    timeout = None if strand.no_timeout else (strand.timeout or 30.0)

    runner = execute_strand_async
    invoker = _create_invoker(
        yarn,
        raw_fn,
        strand.name,
        InvokerConfig(
            args_model=strand.args_schema,
            params=params,
            req_list=list(strand.required) if strand.required else [],
            timeout=timeout,
            tier=tier_val,
        ),
        runner=runner,
    )

    return Strand(
        name=strand.name,
        description=strand.description,
        parameters=params,
        required=list(strand.required) if strand.required else [],
        handler=invoker,
        raw_handler=raw_fn,
        capability=strand.capability,
        args_schema=strand.args_schema,
        tier=tier_val,
        resources=list(strand.resources) if strand.resources else [],
        timeout=timeout,
        no_timeout=strand.no_timeout,
        reason=strand.reason,
        fallback=strand.fallback,
    )


def reflect_strands(yarn: Any) -> list[Strand]:
    """Discover strands on yarn and bind them to Core execution invokers."""
    # If the yarn defines or discovers strands via get_strands(), bind them
    if hasattr(yarn, "get_strands") and callable(yarn.get_strands):
        raw_strands = cast(list[Strand], yarn.get_strands())
        return [bind_strand_to_core(yarn, s) for s in raw_strands]

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
