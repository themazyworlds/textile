"""
Textile Security Functional Domain Package.
Provides security policy gatekeeping (Context), 2FA TOTP verification,
kernel process sandboxing (Sandbox), and resource guardrails (Guardrails).
"""

lazy from needle.guardrails import (
    AccessBoundaryError,
    ScopedPath,
    SessionProcessGuard,
)

from textile.core.definitions.errors import (
    OTPChallengeRequiredError,
    PolicyViolationError,
)
lazy from textile.core.security.context import (
    OTPManager,
    get_totp_secret,
    get_totp_uri,
    global_otp_manager,
    verify_security_policy,
)

__all__ = [
    "AccessBoundaryError",
    "OTPChallengeRequiredError",
    "OTPManager",
    "PolicyViolationError",
    "ScopedPath",
    "SessionProcessGuard",
    "get_totp_secret",
    "get_totp_uri",
    "global_otp_manager",
    "verify_security_policy",
]
