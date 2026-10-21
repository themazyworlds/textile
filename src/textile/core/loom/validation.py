"""
Textile Core Argument Validation and Schema Synthesis.
"""

from __future__ import annotations

from typing import Any, Literal

lazy from pydantic import BaseModel, Field, ValidationError, create_model


def schema_to_model(strand_name: str, parameters: dict[str, Any], required: list[str]) -> type[BaseModel]:
    """Dynamically synthesize a Pydantic BaseModel from JSON schema parameters."""
    fields: dict[str, Any] = {}
    type_map = {"string": str, "integer": int, "number": float, "boolean": bool, "array": list, "object": dict}
    req_set = set(required)
    for p_name, p_spec in parameters.items():
        desc = p_spec.get("description", "")
        enum_vals = p_spec.get("enum")
        t_str = str(p_spec.get("type", "string")).lower()
        _literal_maker: Any = Literal
        field_type: Any = _literal_maker[tuple(enum_vals)] if enum_vals else type_map.get(t_str, Any)
        if p_name in req_set:
            fields[p_name] = (field_type, Field(..., description=desc))
        else:
            fields[p_name] = (field_type | None, Field(default=None, description=desc))
    return create_model(f"{strand_name}_Args", **fields)


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
        real_params = {k: v for k, v in (parameters or {}).items() if k != "otp"}
        if not real_params:
            return None, args.copy()
        try:
            model = schema_to_model(strand_name, parameters or {}, required or [])
        except AttributeError, TypeError, ValueError, KeyError, ValidationError:
            return None, args.copy()

    clean_args = args.copy()
    if empty_err := _check_empty_required_args(strand_name, clean_args, parameters, required):
        return empty_err, args

    try:
        validated = model.model_validate(clean_args)
        return None, {k: v for k, v in validated.model_dump().items() if v is not None}
    except ValidationError as e:
        msg = _format_validation_error(strand_name, args, parameters, e.errors()[0])
        return msg, args


__all__ = ["schema_to_model", "validate_strand_arguments"]
