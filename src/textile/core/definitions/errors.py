"""
Textile Engine Exception Hierarchy.
Provides structured, diagnostic domain exceptions across Textile core & yarns.
"""

from typing import Any

SAFE_EXCEPTIONS = (AttributeError, TypeError, ValueError, KeyError, OSError, RuntimeError)


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
