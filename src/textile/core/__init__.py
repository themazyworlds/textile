"""
Textile Core Fabric Package.
Organized into 5 functional domains: orchestration, security, telemetry, execution, and definitions.
"""

from needle import (
    DEFAULT_LAYER,
    EventOptions,
    Strand,
    StrandNotFoundError,
    Yarn,
    YarnNotFoundError,
    strand,
)
lazy from needle.guardrails import (
    AccessBoundaryError,
    ScopedPath,
    SessionProcessGuard,
)

from textile.core.definitions.errors import (
    PolicyViolationError,
    TextileError,
)
from textile.core.execution.validation import validate_strand_arguments

# Execution
lazy from textile.core.execution.invoker import InvokerConfig

# Orchestration
lazy from textile.core.orchestration.fabric import core_fabric_yarn
lazy from textile.core.orchestration.loom import Loom, loom
lazy from textile.core.orchestration.skein import Skein, skein
lazy from textile.core.orchestration.twill import create_twill_server, run_twill

# Security
lazy from textile.core.security.context import (
    OTPChallengeRequiredError,
    OTPManager,
    get_totp_secret,
    get_totp_uri,
    global_otp_manager,
    verify_security_policy,
)
lazy from textile.core.security.policy import (
    TIER_POLICIES,
    TierPolicy,
    get_tier_policy,
)

# Telemetry
lazy from textile.core.telemetry.blackboard import SensoryTapestry, sensory_tapestry
lazy from textile.core.telemetry.elastic import ElasticEngine, EventFrame, EventUrgency, elastic
lazy from textile.core.telemetry.ledger import CoreTapestry, core_tapestry

__all__ = [
    "DEFAULT_LAYER",
    "AccessBoundaryError",
    "CoreTapestry",
    "ElasticEngine",
    "EventFrame",
    "EventOptions",
    "EventUrgency",
    "InvokerConfig",
    "Loom",
    "OTPChallengeRequiredError",
    "OTPManager",
    "PolicyViolationError",
    "ScopedPath",
    "SensoryTapestry",
    "SessionProcessGuard",
    "Skein",
    "Strand",
    "StrandNotFoundError",
    "TIER_POLICIES",
    "TextileError",
    "TierPolicy",
    "Yarn",
    "YarnNotFoundError",
    "core_fabric_yarn",
    "core_tapestry",
    "create_twill_server",
    "elastic",
    "get_tier_policy",
    "get_totp_secret",
    "get_totp_uri",
    "global_otp_manager",
    "loom",
    "run_twill",
    "sensory_tapestry",
    "skein",
    "strand",
    "validate_strand_arguments",
    "verify_security_policy",
]
