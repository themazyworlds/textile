"""
Textile Core Strand Invoker & Argument Synthesis Factory.
"""

import asyncio
import concurrent.futures
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
    is_strand: bool = True,
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

    if is_strand:
        fields["otp"] = (
            str | None,
            Field(
                default=None,
                description="Optional single-use 4-digit Visual OTP confirmation code displayed on user screen",
            ),
        )

    return create_model(model_name, **fields) if fields else None


@dataclass(slots=True)
class InvokerConfig:
    """Configuration options for synthesizing strand invokers."""

    args_model: type[BaseModel] | None
    params: dict[str, Any]
    req_list: list[str]
    isolated: bool
    timeout: float
    tier: CapabilityTier = CapabilityTier.INTERACT


def _create_invoker(
    yarn: Any,
    method: Callable,
    strand_name: str,
    config: InvokerConfig,
    isolated_runner: Callable[..., str] | None = None,
) -> Callable[[dict[str, Any]], Any]:
    """Create unified asynchronous execution invoker for a strand."""

    def _validate_and_coerce(args: dict[str, Any]) -> tuple[str | None, dict[str, Any]]:
        return validate_strand_arguments(
            strand_name, args, schema_model=config.args_model, parameters=config.params, required=config.req_list
        )

    is_coro = inspect.iscoroutinefunction(method)

    async def _invoker(args: dict[str, Any]) -> str:
        val_err, coerced = _validate_and_coerce(args)
        if val_err:
            return val_err
        coerced.pop("otp", None)
        if config.isolated and isolated_runner is not None:
            return await asyncio.to_thread(
                isolated_runner, yarn, strand_name, coerced, timeout=config.timeout, tier=config.tier
            )
        try:
            if is_coro:
                res = await method(**coerced)
            else:
                res = await asyncio.to_thread(method, **coerced)
            return _format_handler_result(res)
        except STRAND_EXEC_ERRORS as e:
            return f"Error executing strand '{strand_name}': {e}"

    return _invoker


def execute_direct(yarn: Any, strand_name: str, args: dict[str, Any]) -> str:
    """Execute raw or bound strand handler directly with unified validation and async resolution."""
    strands = getattr(yarn, "get_strands", lambda: [])()
    strand = next((s for s in strands if s.name == strand_name), None)
    if strand is None:
        yarn_name = getattr(yarn, "name", yarn.__class__.__name__)
        return f"Error: Strand '{strand_name}' not implemented in yarn '{yarn_name}'."

    val_err, coerced = validate_strand_arguments(
        strand_name,
        args,
        schema_model=strand.args_schema,
        parameters=strand.parameters,
        required=strand.required,
    )
    if val_err:
        return val_err

    coerced.pop("otp", None)

    target_func = strand.raw_handler or strand.handler
    if target_func is None:
        return "ok"

    try:
        is_coro_func = inspect.iscoroutinefunction(target_func)
        if strand.raw_handler is not None:
            raw_h: Any = strand.raw_handler
            sig = inspect.signature(raw_h)
            try:
                bound = sig.bind(**coerced)
                res = raw_h(*bound.args, **bound.kwargs)
            except TypeError:
                res = raw_h(coerced)
        else:
            res = strand.handler(coerced)

        if inspect.iscoroutine(res) or is_coro_func:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop and loop.is_running():
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    res = pool.submit(
                        asyncio.run, res if inspect.iscoroutine(res) else target_func(**coerced)
                    ).result()
            else:
                res = asyncio.run(res if inspect.iscoroutine(res) else target_func(**coerced))

        return _format_handler_result(res)
    except STRAND_EXEC_ERRORS as e:
        return f"Error executing strand '{strand_name}': {e}"

