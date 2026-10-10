"""
Textile Core Fabric Package.
Organized into 5 functional domains: orchestration, security, telemetry, execution, and definitions.
"""

from typing import TYPE_CHECKING, Any

from textile.core.definitions import (
    LayerTier,
    PolicyViolationError,
    StrandNotFoundError,
    TextileError,
    YarnNotFoundError,
    detects_native_ffi,
    get_layer_info,
)
from textile.core.execution import (
    CapabilityTier,
    EventOptions,
    InvokerConfig,
    Strand,
    StrandConfig,
    Weft,
    Yarn,
    strand,
    validate_strand_arguments,
    weft,
)

if TYPE_CHECKING:
    from textile.core.orchestration import (
        Loom,
        Skein,
        core_fabric_yarn,
        create_twill_server,
        loom,
        run_twill,
        skein,
    )
    from textile.core.security import (
        AccessBoundaryError,
        OTPChallengeRequiredError,
        OTPManager,
        ScopedPath,
        SessionProcessGuard,
        get_totp_secret,
        get_totp_uri,
        global_otp_manager,
        verify_security_policy,
    )
    from textile.core.telemetry import (
        CoreTapestry,
        ElasticEngine,
        EventFrame,
        EventUrgency,
        SensoryTapestry,
        core_tapestry,
        elastic,
        sensory_tapestry,
    )

_LAZY_EXPORTS = {
    # Orchestration
    "Loom": ("textile.core.orchestration.loom", "Loom"),
    "loom": ("textile.core.orchestration.loom", "loom"),
    "Skein": ("textile.core.orchestration.skein", "Skein"),
    "skein": ("textile.core.orchestration.skein", "skein"),
    "core_fabric_yarn": ("textile.core.orchestration.fabric", "core_fabric_yarn"),
    "create_twill_server": ("textile.core.orchestration.twill", "create_twill_server"),
    "run_twill": ("textile.core.orchestration.twill", "run_twill"),
    # Security
    "AccessBoundaryError": ("textile.core.security.boundaries", "AccessBoundaryError"),
    "ScopedPath": ("textile.core.security.boundaries", "ScopedPath"),
    "SessionProcessGuard": ("textile.core.security.guard", "SessionProcessGuard"),
    "OTPChallengeRequiredError": ("textile.core.security.context", "OTPChallengeRequiredError"),
    "OTPManager": ("textile.core.security.context", "OTPManager"),
    "global_otp_manager": ("textile.core.security.context", "global_otp_manager"),
    "get_totp_secret": ("textile.core.security.context", "get_totp_secret"),
    "get_totp_uri": ("textile.core.security.context", "get_totp_uri"),
    "verify_security_policy": ("textile.core.security.context", "verify_security_policy"),
    # Telemetry
    "CoreTapestry": ("textile.core.telemetry.ledger", "CoreTapestry"),
    "core_tapestry": ("textile.core.telemetry.ledger", "core_tapestry"),
    "ElasticEngine": ("textile.core.telemetry.elastic", "ElasticEngine"),
    "elastic": ("textile.core.telemetry.elastic", "elastic"),
    "EventFrame": ("textile.core.telemetry.elastic", "EventFrame"),
    "EventUrgency": ("textile.core.telemetry.elastic", "EventUrgency"),
    "SensoryTapestry": ("textile.core.telemetry.blackboard", "SensoryTapestry"),
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
    "AccessBoundaryError",
    "CapabilityTier",
    "CoreTapestry",
    "ElasticEngine",
    "EventFrame",
    "EventOptions",
    "EventUrgency",
    "InvokerConfig",
    "LayerTier",
    "Loom",
    "OTPChallengeRequiredError",
    "OTPManager",
    "PolicyViolationError",
    "ScopedPath",
    "SensoryTapestry",
    "SessionProcessGuard",
    "Skein",
    "Strand",
    "StrandConfig",
    "StrandNotFoundError",
    "TextileError",
    "Weft",
    "Yarn",
    "YarnNotFoundError",
    "core_fabric_yarn",
    "core_tapestry",
    "create_twill_server",
    "detects_native_ffi",
    "elastic",
    "get_layer_info",
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
    "weft",
]
