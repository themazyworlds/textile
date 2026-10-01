"""
Textile Core Layer 2 - Declarative Intent AST & Grammar Schema.
Defines abstract intent nodes for DAG workflow planning.
"""

import re
import uuid
from typing import Any

from pydantic import BaseModel, Field


class IntentValidationError(Exception):
    """Raised when an intent node violates grammar rules."""

    pass


class IntentNode(BaseModel):
    """Declarative Intent Node representing a single high-level system action."""

    intent_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    strand_name: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    otp: str | None = None
    description: str = ""

    def validate_grammar(self) -> None:
        """Sanitize strand_name format."""
        if not re.match(r"^[a-zA-Z0-9_]+$", self.strand_name):
            raise IntentValidationError(f"Invalid strand name format: '{self.strand_name}'")


class IntentGraph(BaseModel):
    """DAG of declarative intent nodes representing a multi-step workflow execution plan."""

    nodes: list[IntentNode] = Field(default_factory=list)

    def append(self, node: IntentNode) -> None:
        node.validate_grammar()
        self.nodes.append(node)
