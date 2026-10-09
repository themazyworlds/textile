"""
Textile Security Functional Domain Package.
Provides security policy gatekeeping (Context), visual OTP verification,
kernel process sandboxing (Sandbox), and resource guardrails (Guardrails).
"""

from textile.core.security.context import (
    OTPChallengeRequiredError,
    OTPManager,
    PendingOTP,
    PolicyViolationError,
    global_otp_manager,
    hash_args,
    verify_security_policy,
)
from textile.core.security.guardrails import (
    AccessBoundaryError,
    ScopedPath,
    SessionProcessGuard,
)

__all__ = [
    "AccessBoundaryError",
    "OTPChallengeRequiredError",
    "OTPManager",
    "PendingOTP",
    "PolicyViolationError",
    "ScopedPath",
    "SessionProcessGuard",
    "global_otp_manager",
    "hash_args",
    "verify_security_policy",
]
