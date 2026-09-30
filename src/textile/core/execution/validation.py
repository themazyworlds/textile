"""
Textile Core Argument Validation, Schema Synthesis, and FFI Inspection.
"""

import logging
import re
import sys
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError, create_model

logger = logging.getLogger(__name__)


def detects_native_ffi(target: Any) -> bool:
    """Detect if a class or module imports native C-FFI modules (ctypes, cffi)."""
    try:
        mod_name = target.__class__.__module__ if hasattr(target, "__class__") else getattr(target, "__module__", "")
        if mod := sys.modules.get(mod_name):
            for val in mod.__dict__.values():
                if getattr(val, "__name__", "") in ("ctypes", "cffi", "_ctypes"):
                    return True
                if isinstance(val, type) and getattr(val, "__module__", "") in ("ctypes", "cffi", "_ctypes"):
                    return True
    except (AttributeError, TypeError, ValueError, RuntimeError) as e:
        logger.debug(f"detects_native_ffi inspection error: {e}")
    return False


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


def validate_strand_schema(strand_name: str, parameters: Any, required: Any) -> list[str]:
    if not isinstance(parameters, dict):
        return [f"Strand '{strand_name}' parameters must be a dictionary."]
    valid_types = {"string", "number", "integer", "boolean", "array", "object"}
    errors = [
        f"Parameter '{p_name}' has invalid specification."
        for p_name, p_spec in parameters.items()
        if not isinstance(p_spec, dict)
        or str(p_spec.get("type", "")).lower() not in valid_types
    ]
    if isinstance(required, list):
        for req in required:
            if req not in parameters:
                errors.append(f"Required field '{req}' not in parameters.")
    return errors


def _check_empty_required_args(
    strand_name: str,
    clean_args: dict[str, Any],
    parameters: dict[str, Any] | None,
    required: list[str] | None,
) -> str | None:
    """Check for required string parameters that are empty or whitespace only."""
    if not required:
        return None
    for r in required:
        if r in clean_args and isinstance(clean_args[r], str) and not clean_args[r].strip():
            p_type = (parameters or {}).get(r, {}).get("type", "value")
            return (
                f"Validation Hint: Strand '{strand_name}' expected required parameter '{r}' "
                f"(type: {p_type}), but it went missing in action!"
            )
    return None


def _format_validation_error(
    strand_name: str,
    args: dict[str, Any],
    parameters: dict[str, Any] | None,
    err: Any,
) -> str:
    """Format Pydantic ValidationError into human-friendly Textile validation hint."""
    loc = str(err["loc"][0]) if err.get("loc") else "parameter"
    err_type = str(err.get("type", ""))
    p_type = (parameters or {}).get(loc, {}).get("type", "value")

    if "missing" in err_type:
        return (
            f"Validation Hint: Strand '{strand_name}' expected required parameter '{loc}' "
            f"(type: {p_type}), but it went missing in action!"
        )
    if "literal" in err_type or "enum" in err_type:
        expected = err.get("ctx", {}).get("expected", "")
        return (
            f"Validation Hint: Invalid action/option '{args.get(loc)}' for strand '{strand_name}'. "
            f"Available options: [{expected}]"
        )
    return f"Validation Hint: Strand '{strand_name}' parameter '{loc}' validation failed: {err.get('msg')}."


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
    if empty_err := _check_empty_required_args(strand_name, clean_args, parameters, required):
        return empty_err, args

    try:
        validated = model.model_validate(clean_args)
        return None, {k: v for k, v in validated.model_dump().items() if v is not None}
    except ValidationError as e:
        msg = _format_validation_error(strand_name, args, parameters, e.errors()[0])
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
