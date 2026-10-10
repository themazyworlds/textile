"""
Textile • Sovereign AI Subsystem & Desktop Intelligence Engine.
"""

from typing import TYPE_CHECKING, Any

from textile.core.definitions import shims
from textile.core.definitions.errors import (
    OTPChallengeRequiredError,
    PolicyViolationError,
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
from textile.core.execution.decorators import strand, weft
from textile.core.execution.strands import CapabilityTier, Strand, Weft
from textile.core.execution.yarn import Yarn

if TYPE_CHECKING:
    from textile.core.orchestration.instructions import fabric_instructions
    from textile.core.orchestration.loom import loom
    from textile.core.orchestration.skein import skein
    from textile.core.orchestration.stream import stream_engine
    from textile.core.telemetry.blackboard import sensory_tapestry
    from textile.core.telemetry.elastic import EventFrame, EventUrgency, elastic
    from textile.core.telemetry.ledger import core_tapestry

__version__ = "0.1.0"

_LAZY_EXPORTS = {
    "loom": ("textile.core.orchestration.loom", "loom"),
    "skein": ("textile.core.orchestration.skein", "skein"),
    "fabric_instructions": ("textile.core.orchestration.instructions", "fabric_instructions"),
    "stream_engine": ("textile.core.orchestration.stream", "stream_engine"),
    "elastic": ("textile.core.telemetry.elastic", "elastic"),
    "EventFrame": ("textile.core.telemetry.elastic", "EventFrame"),
    "EventUrgency": ("textile.core.telemetry.elastic", "EventUrgency"),
    "core_tapestry": ("textile.core.telemetry.ledger", "core_tapestry"),
    "sensory_tapestry": ("textile.core.telemetry.blackboard", "sensory_tapestry"),
}


def __getattr__(name: str) -> Any:
    if name in _LAZY_EXPORTS:
        module_path, attr_name = _LAZY_EXPORTS[name]
        module = __import__(module_path, fromlist=[attr_name])
        val = getattr(module, attr_name)
        globals()[name] = val
        return val
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


def __dir__() -> list[str]:
    return sorted(set(list(globals().keys()) + list(_LAZY_EXPORTS.keys()) + __all__))


__all__ = [
    "LAYER_BASE",
    "LAYER_COMPOSITOR_DE",
    "LAYER_DESKTOP_PROTOCOL",
    "LAYER_SESSION_MANAGER",
    "LAYER_USER_OVERRIDE",
    "CapabilityTier",
    "EventFrame",
    "EventUrgency",
    "OTPChallengeRequiredError",
    "PolicyViolationError",
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
