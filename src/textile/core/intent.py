"""
Textile Core Layer 2 - Declarative Intent AST & Grammar Schema.
Defines abstract intent nodes and sanitizes raw parameters against code injection attempts.
"""

import re
import uuid
from typing import Any

from pydantic import BaseModel, Field

from textile.core.context import OriginToken


class IntentValidationError(Exception):
    """Raised when an intent node violates grammar or contains raw code injection patterns."""
    pass


UNSAFE_INJECTION_PATTERNS = [
    re.compile(r";\s*(?:rm|sudo|pkexec|systemctl|chmod|chown|os\.execute|exec|eval)\b", re.IGNORECASE),
    re.compile(r"&&\s*(?:rm|sudo|pkexec|systemctl|chmod|chown|os\.execute|exec|eval)\b", re.IGNORECASE),
    re.compile(r"\|\|\s*(?:rm|sudo|pkexec|systemctl|chmod|chown|os\.execute|exec|eval)\b", re.IGNORECASE),
    re.compile(r"\b(?:os\.execute|os\.system|subprocess\.Popen|eval\s*\(|exec\s*\()\b", re.IGNORECASE),
]


class IntentNode(BaseModel):
    """Declarative Intent Node representing a single high-level system action."""

    intent_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    strand_name: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    origin_token: OriginToken
    description: str = ""

    def validate_grammar(self) -> None:
        """Sanitize parameters to ensure no raw subshell or code injection strings exist."""
        if not re.match(r"^[a-zA-Z0-9_]+$", self.strand_name):
            raise IntentValidationError(f"Invalid strand name format: '{self.strand_name}'")

        self._check_param_injection(self.parameters)

    def _check_param_injection(self, value: Any) -> None:
        if isinstance(value, str):
            for pattern in UNSAFE_INJECTION_PATTERNS:
                if pattern.search(value):
                    raise IntentValidationError(
                        f"Unsafe code injection pattern detected in intent parameter value: '{value}'"
                    )
        elif isinstance(value, dict):
            for v in value.values():
                self._check_param_injection(v)
        elif isinstance(value, list):
            for item in value:
                self._check_param_injection(item)


class IntentGraph(BaseModel):
    """DAG of declarative intent nodes representing a multi-step workflow execution plan."""

    nodes: list[IntentNode] = Field(default_factory=list)

    def append(self, node: IntentNode) -> None:
        node.validate_grammar()
        self.nodes.append(node)
