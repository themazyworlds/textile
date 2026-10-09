"""
Textile Security Functional Domain Package.
Provides security policy gatekeeping (Context), 2FA TOTP verification,
kernel process sandboxing (Sandbox), and resource guardrails (Guardrails).
"""

from textile.core.security.context import (
    OTPChallengeRequiredError,
    OTPManager,
    PolicyViolationError,
    get_totp_secret,
    get_totp_uri,
    global_otp_manager,
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
    "PolicyViolationError",
    "ScopedPath",
    "SessionProcessGuard",
    "get_totp_secret",
    "get_totp_uri",
    "global_otp_manager",
    "verify_security_policy",
]
