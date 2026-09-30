"""
Textile • Sovereign AI Subsystem & Desktop Intelligence Engine.
"""

from textile.core.contracts.layers import (
    LAYER_COMPOSITOR_DE_THRESHOLD as LAYER_COMPOSITOR_DE,
)
from textile.core.contracts.layers import (
    LAYER_CORE_POSIX_THRESHOLD as LAYER_BASE,
)
from textile.core.contracts.layers import (
    LAYER_DESKTOP_PROTOCOL_THRESHOLD as LAYER_DESKTOP_PROTOCOL,
)
from textile.core.contracts.layers import (
    LAYER_SESSION_MANAGER_THRESHOLD as LAYER_SESSION_MANAGER,
)
from textile.core.contracts.layers import (
    LAYER_USER_OVERRIDE_THRESHOLD as LAYER_USER_OVERRIDE,
)
from textile.core.contracts.manifest import DependenciesManifest, YarnManifest
from textile.core.contracts.sys_detect import detect_shell, detect_terminal, detect_terminal_and_shell
from textile.core.execution.decorators import strand, weft
from textile.core.execution.strands import CapabilityTier, Strand, Weft
from textile.core.execution.yarn import Yarn
from textile.core.telemetry.elastic import EventFrame, EventUrgency, elastic

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
