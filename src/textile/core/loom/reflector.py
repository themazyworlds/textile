"""
Textile Strand Reflection, Factory, and Metadata Extraction.
Converts @strand decorated methods on Yarn instances into Strand objects.
"""

from __future__ import annotations

import inspect
import re
from collections.abc import Callable
from typing import Any, cast

from needle import CapabilityTier
from needle import parse_capability_tier as _parse_tier
from needle.errors import SAFE_EXCEPTIONS
lazy from needle import Strand

lazy from textile.core.camshaft import camshaft

__all__ = [
    "bind_strand_to_core",
    "method_to_strand",
    "reflect_strands",
]


def _extract_docstring_info(doc: str | None) -> tuple[str, dict[str, str]]:
    """Parse method docstring into description and parameter documentation map."""
    if not doc:
        return "", {}
    desc_lines, param_docs = [], {}
    in_summary = True
    for line in doc.strip().splitlines():
        s = line.strip()
        if not s:
            in_summary = False
            continue
        m = re.match(r":param\s+([a-zA-Z0-9_]+):\s*(.*)", s) or re.match(r"([a-zA-Z0-9_]+)(?:\s*\([^)]*\))?:\s+(.*)", s)
        if m and not s.startswith(("http:", "https:", "Note:", "Warning:", "Returns:", "Yields:", "NOTE:", "WARNING:")):
            in_summary = False
            param_docs[m.group(1)] = m.group(2)
        elif in_summary:
            if s.startswith(("Note:", "Warning:", "Returns:", "Yields:", "NOTE:", "WARNING:", "Example:", "EXAMPLE:")):
                in_summary = False
            else:
                desc_lines.append(s)
    summary = " ".join(desc_lines).strip()
    return summary, param_docs


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

    s_reason = getattr(method, "_strand_reason", None)
    s_fallback = getattr(method, "_strand_fallback", None)
    s_resources = getattr(method, "_strand_resources", list(getattr(yarn, "resources", [])))

    return Strand(
        name=strand_name,
        description=strand_desc,
        parameters=params,
        required=req_list,
        handler=method,
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
    """Bind a raw SDK or custom strand to Core schema conventions."""
    raw_fn = strand.raw_handler or strand.handler
    if raw_fn is None:
        return strand

    params = dict(strand.parameters) if strand.parameters else {}
    if "otp" not in params:
        params["otp"] = {
            "type": "string",
            "description": "Optional single-use 6-digit 2FA confirmation code displayed on user screen",
        }

    tier_val = _parse_tier(strand.tier, strand.name)
    timeout = None if strand.no_timeout else (strand.timeout or 30.0)

    s_resources = list(strand.resources) if strand.resources else list(getattr(yarn, "resources", []))

    return Strand(
        name=strand.name,
        description=strand.description,
        parameters=params,
        required=list(strand.required) if strand.required else [],
        handler=raw_fn,
        raw_handler=raw_fn,
        capability=strand.capability,
        args_schema=strand.args_schema,
        tier=tier_val,
        resources=s_resources,
        timeout=timeout,
        no_timeout=strand.no_timeout,
        reason=strand.reason,
        fallback=strand.fallback,
    )


def reflect_strands(yarn: Any) -> list[Strand]:
    """Discover strands on yarn and bind them to Core execution schemas."""
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
            camshaft.stitch_notice(
                level="DEBUG",
                source="reflector",
                message=f"Reflection attribute error on '{attr_name}': {e}",
                data={"attribute": attr_name, "error": str(e)},
            )
            continue
        if callable(unbound) and getattr(unbound, "_is_strand", False):
            bound = getattr(yarn, attr_name)
            discovered.append(method_to_strand(yarn, bound))
    return discovered
