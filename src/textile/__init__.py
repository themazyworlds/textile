"""
Textile • Sovereign AI Subsystem & Desktop Intelligence Engine.
"""

from needle import (
    LAYER_COMPOSITOR_DE_THRESHOLD as LAYER_COMPOSITOR_DE,
)
from needle import (
    LAYER_CORE_POSIX_THRESHOLD as LAYER_BASE,
)
from needle import (
    LAYER_DESKTOP_PROTOCOL_THRESHOLD as LAYER_DESKTOP_PROTOCOL,
)
from needle import (
    LAYER_SESSION_MANAGER_THRESHOLD as LAYER_SESSION_MANAGER,
)
from needle import (
    LAYER_USER_OVERRIDE_THRESHOLD as LAYER_USER_OVERRIDE,
)
from needle import (
    CapabilityTier,
    Strand,
    StrandCollisionError,
    StrandNotFoundError,
    StrandOperationalError,
    Yarn,
    YarnNotFoundError,
    strand,
)

from textile.core.definitions.errors import (
    OTPChallengeRequiredError,
    PolicyViolationError,
    SandboxUnavailableError,
    TextileError,
)

__version__ = "0.1.0"

lazy from textile.core.orchestration.instructions import fabric_instructions
lazy from textile.core.orchestration.loom import loom
lazy from textile.core.orchestration.skein import skein
lazy from textile.core.telemetry.blackboard import sensory_tapestry
lazy from textile.core.telemetry.elastic import EventFrame, EventUrgency, elastic
lazy from textile.core.telemetry.ledger import core_tapestry

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
    "Yarn",
    "YarnNotFoundError",
    "__version__",
    "core_tapestry",
    "elastic",
    "fabric_instructions",
    "loom",
    "sensory_tapestry",
    "skein",
    "strand",
]
