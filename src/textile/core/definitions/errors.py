"""
Textile Engine Exception Hierarchy.
Provides structured, diagnostic domain exceptions across Textile core & yarns.
"""

from typing import Any

SAFE_EXCEPTIONS = (AttributeError, TypeError, ValueError, KeyError, OSError, RuntimeError, ImportError)


class TextileError(Exception):
    """Base domain exception for Textile engine operations."""

    def __init__(
        self,
        message: str,
        hint: str | None = None,
        code: str = "ERR_TEXTILE",
        details: dict[str, Any] | None = None,
    ):
        super().__init__(message)
        self.message = message
        self.hint = hint
        self.code = code
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        res: dict[str, Any] = {
            "status": "error",
            "code": self.code,
            "message": self.message,
        }
        if self.hint:
            res["hint"] = self.hint
        if self.details:
            res["details"] = self.details
        return res

    def __str__(self) -> str:
        base = f"[{self.code}] {self.message}"
        if self.hint:
            base += f" (Hint: {self.hint})"
        return base


class StrandNotFoundError(TextileError):
    """Raised when a requested strand is not registered or active in Skein/Loom."""

    def __init__(self, strand_name: str, available_strands: list[str] | None = None):
        top_matches = sorted(available_strands[:5]) if available_strands else []
        hint_msg = (
            f"Did you mean one of: {', '.join(top_matches)}?"
            if top_matches
            else "Use 'textile strands' to inspect available strands."
        )
        super().__init__(
            message=f"Strand '{strand_name}' not found.",
            hint=hint_msg,
            code="ERR_STRAND_NOT_FOUND",
            details={"strand": strand_name},
        )


class YarnNotFoundError(TextileError):
    """Raised when a requested yarn is not registered or active."""

    def __init__(self, yarn_name: str, available_yarns: list[str] | None = None):
        top_matches = sorted(available_yarns[:5]) if available_yarns else []
        hint_msg = (
            f"Did you mean one of: {', '.join(top_matches)}?"
            if top_matches
            else "Use 'textile yarns' to inspect available yarns."
        )
        super().__init__(
            message=f"Yarn '{yarn_name}' not found.",
            hint=hint_msg,
            code="ERR_YARN_NOT_FOUND",
            details={"yarn": yarn_name},
        )


class SandboxUnavailableError(TextileError):
    """Raised when process isolation is requested or required, but sandbox tools (bwrap) are unavailable."""

    def __init__(self, reason: str):
        super().__init__(
            message=f"Sandbox isolation unavailable: {reason}",
            hint="Install 'bubblewrap' (bwrap) or run in an environment with container namespace support.",
            code="ERR_SANDBOX_UNAVAILABLE",
        )


class StrandCollisionError(TextileError):
    """Raised when two Yarns register identical strand names without a capability contract."""

    def __init__(self, strand_name: str, existing_yarn: str, new_yarn: str):
        msg = (
            f"Strand collision detected: '{strand_name}' registered by both "
            f"'{existing_yarn}' and '{new_yarn}' without a capability contract."
        )
        super().__init__(
            message=msg,
            hint="Declare explicit 'capability' on both strands to allow layer-based overrides.",
            code="ERR_STRAND_COLLISION",
            details={"strand": strand_name, "existing_yarn": existing_yarn, "new_yarn": new_yarn},
        )


class StrandOperationalError(TextileError):
    """Raised when a strand execution fails during underlying tool execution (distinct from security/OTP errors)."""

    def __init__(self, strand_name: str, reason: str, original_error: Exception | None = None):
        super().__init__(
            message=reason,
            hint="Inspect operational details. OTP verification succeeded; this is a system/tool error.",
            code="ERR_STRAND_OPERATIONAL",
            details={"strand": strand_name, "original_error": str(original_error) if original_error else None},
        )


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


