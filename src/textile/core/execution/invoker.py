"""
Textile Core Strand Invoker & Argument Synthesis Factory.
"""

import inspect
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, get_type_hints

from pydantic import BaseModel, Field, create_model

from textile.core.definitions.errors import TextileError
from textile.core.execution.strands import CapabilityTier
from textile.core.execution.validation import validate_strand_arguments

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


def _format_handler_result(res: Any) -> str:
    """Format handler execution output into string or formatted JSON."""
    if isinstance(res, (dict, list)):
        return json.dumps(res, indent=2)
    return str(res) if res is not None else "ok"


def _build_args_model(
    method: Callable,
    model_name: str,
    param_docs: dict[str, str] | None = None,
) -> type[BaseModel] | None:
    """Helper to synthesize Pydantic BaseModel for method parameters."""
    sig = inspect.signature(method)
    try:
        hints = get_type_hints(method)
    except (AttributeError, TypeError, NameError, ValueError, KeyError):
        hints = {}

    docs = param_docs or {}
    fields = {}
    for p_name, param in sig.parameters.items():
        if p_name in ("self", "cls"):
            continue
        p_type = hints.get(p_name, Any)
        p_desc = docs.get(p_name, "")
        if param.default is inspect.Parameter.empty:
            fields[p_name] = (p_type, Field(..., description=p_desc))
        else:
            fields[p_name] = (p_type, Field(default=param.default, description=p_desc))

    return create_model(model_name, **fields) if fields else None


@dataclass(slots=True)
class InvokerConfig:
    """Configuration options for synthesizing strand invokers."""

    args_model: type[BaseModel] | None
    params: dict[str, Any]
    req_list: list[str]
    isolated: bool
    is_async: bool
    timeout: float
    tier: CapabilityTier = CapabilityTier.INTERACT


def _create_invoker(
    yarn: Any,
    method: Callable,
    strand_name: str,
    config: InvokerConfig,
) -> Callable[[dict[str, Any]], Any]:
    """Create unified sync or async execution invoker for a strand."""

    def _validate_and_coerce(args: dict[str, Any]) -> tuple[str | None, dict[str, Any]]:
        return validate_strand_arguments(
            strand_name, args, schema_model=config.args_model, parameters=config.params, required=config.req_list
        )

    if config.is_async:

        async def _async_invoker(args: dict[str, Any]) -> str:
            val_err, coerced = _validate_and_coerce(args)
            if val_err:
                return val_err
            try:
                res = await method(**coerced)
                return _format_handler_result(res)
            except STRAND_EXEC_ERRORS as e:
                return f"Error executing strand '{strand_name}': {e}"

        return _async_invoker

    def _sync_invoker(args: dict[str, Any]) -> str:
        val_err, coerced = _validate_and_coerce(args)
        if val_err:
            return val_err
        if config.isolated:
            return yarn._run_isolated(strand_name, coerced, timeout=config.timeout, tier=config.tier)
        try:
            res = method(**coerced)
            return _format_handler_result(res)
        except STRAND_EXEC_ERRORS as e:
            return f"Error executing strand '{strand_name}': {e}"

    return _sync_invoker
