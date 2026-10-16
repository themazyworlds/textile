"""
Textile • Sovereign AI Subsystem & Desktop Intelligence Engine.
"""

from needle import (
    DEFAULT_LAYER,
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
    "DEFAULT_LAYER",
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
