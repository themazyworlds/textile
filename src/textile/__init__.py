"""
Textile • Modular AI Subsystem & Desktop Intelligence Engine.
"""

from textile.core.base import (
    LAYER_BASE,
    LAYER_COMPOSITOR_DE,
    LAYER_DESKTOP_PROTOCOL,
    LAYER_SESSION_MANAGER,
    LAYER_USER_OVERRIDE,
    CapabilityTier,
    Yarn,
    strand,
    weft,
)

__version__ = "0.1.0"

__all__ = [
    "Yarn",
    "CapabilityTier",
    "strand",
    "weft",
    "LAYER_BASE",
    "LAYER_DESKTOP_PROTOCOL",
    "LAYER_COMPOSITOR_DE",
    "LAYER_SESSION_MANAGER",
    "LAYER_USER_OVERRIDE",
    "__version__",
]
