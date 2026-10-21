"""
Textile Core Strand In-Process Invoker & Output Formatter.
Provides direct in-process callable execution and output formatting.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any
lazy import asyncio
lazy import concurrent.futures

import orjson
from needle import CapabilityTier
lazy from needle import Strand
lazy from pydantic import BaseModel


def format_handler_result(res: Any) -> str:
    """Format handler execution output into string or formatted JSON."""
    if isinstance(res, (dict, list)):
        return orjson.dumps(res, option=orjson.OPT_INDENT_2).decode()
    return str(res) if res is not None else "ok"


_format_handler_result = format_handler_result


@dataclass(slots=True)
class InvokerConfig:
    """Configuration options for synthesizing strand invokers."""

    args_model: type[BaseModel] | None = None
    params: dict[str, Any] | None = None
    req_list: list[str] | None = None
    timeout: float | None = 30.0
    tier: CapabilityTier = CapabilityTier.INTERACT


async def execute_in_process(strand: Strand, args: dict[str, Any]) -> str:
    """Execute a strand handler directly in-process (async or thread pool)."""
    fn = strand.raw_handler or strand.handler
    if fn is None:
        return "ok"

    sig = inspect.signature(fn)
    try:
        bound = sig.bind(**args)
        call_args, call_kwargs = bound.args, bound.kwargs
    except TypeError:
        call_args, call_kwargs = (args,), {}

    try:
        if inspect.iscoroutinefunction(fn):
            res = await fn(*call_args, **call_kwargs)
        else:
            res = await asyncio.to_thread(fn, *call_args, **call_kwargs)
            if inspect.iscoroutine(res):
                res = await res
        return format_handler_result(res)
    except (TypeError, ValueError, RuntimeError, OSError, KeyError, AttributeError) as e:
        return f"Error executing strand '{strand.name}': {e}"


def execute_direct(yarn: Any, strand_name: str, args: dict[str, Any]) -> str:
    """Execute raw or bound strand handler directly with async resolution."""
    strands = getattr(yarn, "get_strands", list)()
    strand = next((s for s in strands if s.name == strand_name), None)
    if strand is None:
        yarn_name = getattr(yarn, "name", yarn.__class__.__name__)
        return f"Error: Strand '{strand_name}' not implemented in yarn '{yarn_name}'."

    coerced = args.copy()
    coerced.pop("otp", None)

    target_func = strand.raw_handler or strand.handler
    if target_func is None:
        return "ok"

    try:
        is_coro_func = inspect.iscoroutinefunction(target_func)
        sig = inspect.signature(target_func)
        try:
            bound = sig.bind(**coerced)
            call_args, call_kwargs = bound.args, bound.kwargs
        except TypeError:
            call_args, call_kwargs = (coerced,), {}

        res = target_func(*call_args, **call_kwargs)

        if inspect.iscoroutine(res) or is_coro_func:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop and loop.is_running():
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    res = pool.submit(asyncio.run, res if inspect.iscoroutine(res) else target_func(**coerced)).result()
            else:
                res = asyncio.run(res if inspect.iscoroutine(res) else target_func(**coerced))

        return format_handler_result(res)
    except (TypeError, ValueError, RuntimeError, OSError, KeyError, AttributeError) as e:
        return f"Error executing strand '{strand_name}': {e}"


__all__ = [
    "InvokerConfig",
    "execute_direct",
    "execute_in_process",
    "format_handler_result",
]
