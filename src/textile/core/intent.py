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


# Detects shell execution *mechanisms* (subshells, backticks, Python exec primitives).
# We do NOT blacklist specific command names — those are meaningless without a shell interpreter.
# These patterns catch the structural primitives that would be dangerous in *any* language.
SHELL_EXEC_PRIMITIVES = [
    re.compile(r"\$\("),                                          # Subshell: $(...)
    re.compile(r"`[^`]+`"),                                       # Backtick subshell: `cmd`
    re.compile(r"\b(?:eval|exec)\s*\(", re.IGNORECASE),          # Python eval(/exec( calls
    re.compile(r"\bos\.system\s*\(", re.IGNORECASE),             # os.system(
    re.compile(r"\bsubprocess\s*\.", re.IGNORECASE),              # subprocess.* calls
    re.compile(r"\bimportlib\s*\.\s*import_module\s*\(", re.IGNORECASE),  # Dynamic imports
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
            for pattern in SHELL_EXEC_PRIMITIVES:
                if pattern.search(value):
                    raise IntentValidationError(
                        f"Shell execution primitive detected in intent parameter: '{value}'"
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
