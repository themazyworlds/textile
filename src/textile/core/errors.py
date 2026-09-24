"""
Textile Engine Exception Hierarchy.
Provides structured, diagnostic domain exceptions across Textile core & yarns.
"""

from typing import Any


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


class StrandExecutionError(TextileError):
    """Raised when a desktop strand encounters a runtime error during execution."""

    def __init__(self, strand_name: str, reason: str, hint: str | None = None):
        super().__init__(
            message=f"Error executing strand '{strand_name}': {reason}",
            hint=hint or f"Verify arguments and system availability for strand '{strand_name}'.",
            code="ERR_STRAND_EXECUTION",
            details={"strand": strand_name, "reason": reason},
        )


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


class StrandValidationError(TextileError):
    """Raised when argument type checking or schema validation fails for a strand."""

    def __init__(self, strand_name: str, details: str, hint: str | None = None):
        super().__init__(
            message=f"Validation failed for strand '{strand_name}': {details}",
            hint=hint or "Verify parameter types and required fields.",
            code="ERR_STRAND_VALIDATION",
            details={"strand": strand_name, "validation_error": details},
        )


class TargetNotFoundError(TextileError):
    """Raised when a target desktop element (window, workspace, process, unit) is missing."""

    def __init__(self, target_type: str, target_id: str, hint: str | None = None):
        super().__init__(
            message=f"{target_type.capitalize()} '{target_id}' not found.",
            hint=hint or f"Verify the target {target_type} identifier and status.",
            code="ERR_TARGET_NOT_FOUND",
            details={"target_type": target_type, "target_id": target_id},
        )


class PermissionDeniedError(TextileError):
    """Raised when security boundary or capability tier blocks execution."""

    def __init__(self, strand_name: str, required_tier: str, trust_level: str = "NONE"):
        super().__init__(
            message=(
                f"Access denied executing strand '{strand_name}' "
                f"(requires tier '{required_tier}' under trust level '{trust_level}')."
            ),
            hint="Elevate trust level or adjust security desk policy.",
            code="ERR_PERMISSION_DENIED",
            details={
                "strand": strand_name,
                "required_tier": required_tier,
                "trust_level": trust_level,
            },
        )
