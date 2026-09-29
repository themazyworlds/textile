"""
Textile • Sovereign AI Subsystem & Desktop Intelligence Engine.
"""

from textile.core.decorators import strand, weft
from textile.core.elastic import EventFrame, EventUrgency, elastic
from textile.core.manifest import (
    LAYER_BASE,
    LAYER_COMPOSITOR_DE,
    LAYER_DESKTOP_PROTOCOL,
    LAYER_SESSION_MANAGER,
    LAYER_USER_OVERRIDE,
    DependenciesManifest,
    YarnManifest,
)
from textile.core.strands import CapabilityTier, Strand, Weft
from textile.core.sys_detect import detect_shell, detect_terminal, detect_terminal_and_shell
from textile.core.yarn import Yarn

__version__ = "0.1.0"

__all__ = [
    "LAYER_BASE",
    "LAYER_COMPOSITOR_DE",
    "LAYER_DESKTOP_PROTOCOL",
    "LAYER_SESSION_MANAGER",
    "LAYER_USER_OVERRIDE",
    "CapabilityTier",
    "DependenciesManifest",
    "EventFrame",
    "EventUrgency",
    "Strand",
    "Weft",
    "Yarn",
    "YarnManifest",
    "__version__",
    "detect_shell",
    "detect_terminal",
    "detect_terminal_and_shell",
    "elastic",
    "strand",
    "weft",
]
