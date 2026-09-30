"""
Textile Security Functional Domain Package.
Provides security policy gatekeeping (Context), kernel process sandboxing (Sandbox),
sandbox desks (Desks), and resource guardrails (Guardrails).
"""

from textile.core.security.context import (
    OriginToken,
    PolicyViolationError,
    TrustLevel,
    verify_security_policy,
)
from textile.core.security.desks import (
    InteractDesk,
    MutateDesk,
    ObserverDesk,
    PrivilegedDesk,
)
from textile.core.security.guardrails import (
    AccessBoundaryError,
    SafeExec,
    ScopedPath,
    SessionProcessGuard,
)
from textile.core.security.sandbox import BubblewrapSandbox, LandlockSandbox

__all__ = [
    "AccessBoundaryError",
    "BubblewrapSandbox",
    "InteractDesk",
    "LandlockSandbox",
    "MutateDesk",
    "ObserverDesk",
    "OriginToken",
    "PolicyViolationError",
    "PrivilegedDesk",
    "SafeExec",
    "ScopedPath",
    "SessionProcessGuard",
    "TrustLevel",
    "verify_security_policy",
]
