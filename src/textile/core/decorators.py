"""
Textile Core Strand & Weft Decorators.
"""

import re
from collections.abc import Callable
from typing import Any, Literal

from textile.core.strands import CapabilityTier


def _parse_tier(raw_tier: Any, strand_name: str = "") -> CapabilityTier:
    """Parse and validate a capability tier value, failing closed on invalid tiers."""
    if isinstance(raw_tier, CapabilityTier):
        return raw_tier
    if isinstance(raw_tier, str):
        try:
            return CapabilityTier(raw_tier.lower())
        except ValueError:
            pass
    raise ValueError(
        f"Strand '{strand_name or 'unknown'}' must explicitly specify a valid CapabilityTier "
        "(e.g., tier=CapabilityTier.OBSERVE, CapabilityTier.INTERACT, "
        "CapabilityTier.MUTATE, CapabilityTier.PRIVILEGED, or CapabilityTier.SYSTEM_EXEC)."
    )


def strand(
    func: Callable | None = None,
    *,
    name: str | None = None,
    description: str | None = None,
    capability: str | None = None,
    tier: CapabilityTier | Literal["observe", "interact", "mutate", "privileged", "system_exec"] | None = None,
    isolated: bool | None = None,
    timeout: float = 30.0,
):
    """Decorator marking a Yarn method as an executable Desktop Strand."""
    if tier is None:
        raise ValueError(
            "Strand decorator must explicitly declare a capability tier "
            "(e.g., @strand(..., tier='observe') or @strand(..., tier='interact'))."
        )

    def decorator(fn: Any) -> Any:
        setattr(fn, "_is_strand", True)
        setattr(fn, "_strand_name", name or getattr(fn, "__name__", ""))
        setattr(fn, "_strand_description", description)
        setattr(fn, "_strand_capability", capability)
        setattr(fn, "_strand_tier", tier)
        setattr(fn, "_strand_isolated", isolated)
        setattr(fn, "_strand_timeout", timeout)
        return fn

    return decorator(func) if func is not None else decorator


def weft(
    func: Callable | None = None,
    *,
    pattern: str | re.Pattern,
    name: str | None = None,
    description: str | None = None,
    strip: bool = True,
    priority: int = 100,
):
    """Decorator marking a Yarn method as a real-time streaming token Weft attunement."""
    compiled_pattern = re.compile(pattern) if isinstance(pattern, str) else pattern

    def decorator(fn: Any) -> Any:
        setattr(fn, "_is_weft", True)
        setattr(fn, "_weft_name", name or getattr(fn, "__name__", ""))
        setattr(fn, "_weft_pattern", compiled_pattern)
        setattr(fn, "_weft_description", description)
        setattr(fn, "_weft_strip", strip)
        setattr(fn, "_weft_priority", priority)
        return fn

    return decorator(func) if func is not None else decorator
