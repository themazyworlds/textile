"""
Textile Engine Exception Hierarchy.
Provides structured, diagnostic domain exceptions specific to Textile core runtime.
"""

from typing import Any

from hem import SandboxUnavailableError
from needle.errors import NeedleError


class TextileError(NeedleError):
    """Base domain exception for Textile engine operations."""

    def __init__(
        self,
        message: str,
        hint: str | None = None,
        code: str = "ERR_TEXTILE",
        details: dict[str, Any] | None = None,
    ):
        super().__init__(message=message, hint=hint, code=code, details=details)


class PolicyViolationError(PermissionError):
    """Raised when an operation violates security policy (e.g. invalid/expired 2FA code)."""


class OTPChallengeRequiredError(PermissionError):
    """Raised when a MUTATE, PRIVILEGED, or SYSTEM_EXEC strand requires 2FA confirmation."""

    def __init__(self, strand_name: str) -> None:
        self.strand_name = strand_name
        super().__init__(
            f"2FA Confirmation Required for '{strand_name}'. "
            f"Pass current 6-digit Authenticator code via otp='<6_digit_code>'."
        )


STRAND_EXEC_ERRORS: tuple[type[Exception], ...] = (
    TextileError,
    AttributeError,
    TypeError,
    ValueError,
    KeyError,
    OSError,
    RuntimeError,
)


__all__ = [
    "OTPChallengeRequiredError",
    "PolicyViolationError",
    "STRAND_EXEC_ERRORS",
    "SandboxUnavailableError",
    "TextileError",
]
