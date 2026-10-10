"""
Textile Security Functional Domain Package.
Provides security policy gatekeeping (Context), 2FA TOTP verification,
kernel process sandboxing (Sandbox), and resource guardrails (Guardrails).
"""

from typing import TYPE_CHECKING, Any

from textile.core.definitions.errors import (
    OTPChallengeRequiredError,
    PolicyViolationError,
)

if TYPE_CHECKING:
    from textile.core.security.context import (
        OTPManager,
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

_LAZY_EXPORTS = {
    "OTPManager": ("textile.core.security.context", "OTPManager"),
    "global_otp_manager": ("textile.core.security.context", "global_otp_manager"),
    "get_totp_secret": ("textile.core.security.context", "get_totp_secret"),
    "get_totp_uri": ("textile.core.security.context", "get_totp_uri"),
    "verify_security_policy": ("textile.core.security.context", "verify_security_policy"),
    "AccessBoundaryError": ("textile.core.security.guardrails", "AccessBoundaryError"),
    "ScopedPath": ("textile.core.security.guardrails", "ScopedPath"),
    "SessionProcessGuard": ("textile.core.security.guardrails", "SessionProcessGuard"),
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
