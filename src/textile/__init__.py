"""
Textile • Sovereign AI Subsystem & Desktop Intelligence Engine.
"""

from textile.core.definitions import shims
from textile.core.definitions.errors import (
    SandboxUnavailableError,
    StrandCollisionError,
    StrandNotFoundError,
    StrandOperationalError,
    TextileError,
    YarnNotFoundError,
)
from textile.core.definitions.layers import (
    LAYER_COMPOSITOR_DE_THRESHOLD as LAYER_COMPOSITOR_DE,
)
from textile.core.definitions.layers import (
    LAYER_CORE_POSIX_THRESHOLD as LAYER_BASE,
)
from textile.core.definitions.layers import (
    LAYER_DESKTOP_PROTOCOL_THRESHOLD as LAYER_DESKTOP_PROTOCOL,
)
from textile.core.definitions.layers import (
    LAYER_SESSION_MANAGER_THRESHOLD as LAYER_SESSION_MANAGER,
)
from textile.core.definitions.layers import (
    LAYER_USER_OVERRIDE_THRESHOLD as LAYER_USER_OVERRIDE,
)
from textile.core.definitions.sys_detect import detect_shell, detect_terminal, detect_terminal_and_shell
from textile.core.execution.decorators import strand, weft
from textile.core.execution.strands import CapabilityTier, Strand, Weft
from textile.core.execution.yarn import Yarn
from textile.core.orchestration.instructions import fabric_instructions
from textile.core.orchestration.loom import loom
from textile.core.orchestration.skein import skein
from textile.core.orchestration.stream import stream_engine
from textile.core.telemetry.blackboard import sensory_tapestry
from textile.core.telemetry.elastic import EventFrame, EventUrgency, elastic
from textile.core.telemetry.ledger import core_tapestry

__version__ = "0.1.0"

__all__ = [
    "LAYER_BASE",
    "LAYER_COMPOSITOR_DE",
    "LAYER_DESKTOP_PROTOCOL",
    "LAYER_SESSION_MANAGER",
    "LAYER_USER_OVERRIDE",
    "CapabilityTier",
    "EventFrame",
    "EventUrgency",
    "SandboxUnavailableError",
    "Strand",
    "StrandCollisionError",
    "StrandNotFoundError",
    "StrandOperationalError",
    "TextileError",
    "Weft",
    "Yarn",
    "YarnNotFoundError",
    "__version__",
    "core_tapestry",
    "detect_shell",
    "detect_terminal",
    "detect_terminal_and_shell",
    "elastic",
    "fabric_instructions",
    "loom",
    "sensory_tapestry",
    "shims",
    "skein",
    "strand",
    "stream_engine",
    "weft",
]
