"""
Textile Core Strand & Weft Decorators.
"""

import re
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from typing import Any, Literal

from textile.core.execution.strands import CapabilityTier


def _parse_tier(raw_tier: Any, strand_name: str = "") -> CapabilityTier:
    """Parse and validate a capability tier value, failing closed on invalid tiers."""
    if isinstance(raw_tier, CapabilityTier):
        return raw_tier
    if isinstance(raw_tier, str):
        with suppress(ValueError):
            return CapabilityTier(raw_tier.lower())
    raise ValueError(
        f"Strand '{strand_name or 'unknown'}' must explicitly specify a valid CapabilityTier "
        "(e.g., tier=CapabilityTier.OBSERVE, CapabilityTier.INTERACT, "
        "CapabilityTier.MUTATE, CapabilityTier.PRIVILEGED, or CapabilityTier.SYSTEM_EXEC)."
    )


@dataclass(slots=True)
class StrandDecoratorOptions:
    name: str | None = None
    description: str | None = None
    capability: str | None = None
    tier: CapabilityTier | Literal["observe", "interact", "mutate", "privileged", "system_exec"] | None = None
    timeout: float | None = 30.0
    no_timeout: bool = False


@dataclass(slots=True)
class WeftDecoratorOptions:
    pattern: str | re.Pattern = ""
    name: str | None = None
    description: str | None = None
    strip: bool = True
    priority: int = 100


def strand(
    func: Callable | None = None,
    options: StrandDecoratorOptions | None = None,
    **kwargs: Any,
):
    """Decorator marking a Yarn method as an executable Desktop Strand."""
    opts = options or StrandDecoratorOptions(**kwargs)
    if opts.tier is None:
        raise ValueError(
            "Strand decorator must explicitly declare a capability tier "
            "(e.g., @strand(..., tier='observe') or @strand(..., tier='interact'))."
        )

    def decorator(fn: Any) -> Any:
        setattr(fn, "_is_strand", True)
        setattr(fn, "_strand_name", opts.name or getattr(fn, "__name__", ""))
        setattr(fn, "_strand_description", opts.description)
        setattr(fn, "_strand_capability", opts.capability)
        setattr(fn, "_strand_tier", opts.tier)
        setattr(fn, "_strand_timeout", opts.timeout)
        setattr(fn, "_strand_no_timeout", opts.no_timeout)
        return fn

    return decorator(func) if func is not None else decorator


def weft(
    func: Callable | None = None,
    options: WeftDecoratorOptions | None = None,
    **kwargs: Any,
):
    """Decorator marking a Yarn method as a real-time streaming token Weft attunement."""
    opts = options or WeftDecoratorOptions(**kwargs)
    compiled_pattern = re.compile(opts.pattern) if isinstance(opts.pattern, str) else opts.pattern

    def decorator(fn: Any) -> Any:
        setattr(fn, "_is_weft", True)
        setattr(fn, "_weft_name", opts.name or getattr(fn, "__name__", ""))
        setattr(fn, "_weft_pattern", compiled_pattern)
        setattr(fn, "_weft_description", opts.description)
        setattr(fn, "_weft_strip", opts.strip)
        setattr(fn, "_weft_priority", opts.priority)
        return fn

    return decorator(func) if func is not None else decorator
