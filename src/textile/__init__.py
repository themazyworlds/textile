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
    detect_shell,
    detect_terminal,
    detect_terminal_and_shell,
    strand,
    weft,
)
from textile.core.elastic import EventFrame, EventUrgency, elastic

__version__ = "0.1.0"

__all__ = [
    "Yarn",
    "CapabilityTier",
    "strand",
    "weft",
    "detect_terminal",
    "detect_shell",
    "detect_terminal_and_shell",
    "elastic",
    "EventFrame",
    "EventUrgency",
    "LAYER_BASE",
    "LAYER_DESKTOP_PROTOCOL",
    "LAYER_COMPOSITOR_DE",
    "LAYER_SESSION_MANAGER",
    "LAYER_USER_OVERRIDE",
    "__version__",
]
