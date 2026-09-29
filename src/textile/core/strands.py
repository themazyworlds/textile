"""
Textile Core Strand, Weft, and Capability Tier Specifications.
"""

import logging
import re
from collections.abc import Callable
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

logger = logging.getLogger(__name__)


class CapabilityTier(StrEnum):
    """Execution risk & privilege tiers for Textile Strands."""

    OBSERVE = "observe"  # Read-only telemetry, state inspection, queries, logs
    INTERACT = "interact"  # Desktop GUI interactions, notifications, clipboard, media
    MUTATE = "mutate"  # File modifications, killing user processes, local workspace changes
    PRIVILEGED = "privileged"  # System configuration, package installs, D-Bus system calls, Polkit
    SYSTEM_EXEC = "system_exec"  # Arbitrary shell command execution (auto-isolated)


class Strand(BaseModel):
    """Represents a single callable tool/strand exposed by a yarn."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    description: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    handler: Callable[[dict[str, Any]], str] | None = None
    required: list[str] = Field(default_factory=list)
    raw_handler: Callable[[dict[str, Any]], Any] | None = None
    capability: str | None = None
    args_schema: type[BaseModel] | None = None
    tier: CapabilityTier = CapabilityTier.INTERACT
    isolated: bool = False
    resources: list[str] = Field(default_factory=list)

    def to_mcp_definition(self) -> dict[str, Any]:
        """Convert strand schema into Model Context Protocol format."""
        tier_str = str(self.tier.value).upper() if hasattr(self.tier, "value") else str(self.tier).upper()
        desc = f"[Capability Tier: {tier_str}] {self.description}"
        if self.args_schema:
            return {
                "name": self.name,
                "description": desc,
                "inputSchema": self.args_schema.model_json_schema(),
            }
        return {
            "name": self.name,
            "description": desc,
            "inputSchema": {
                "type": "object",
                "properties": self.parameters,
                "required": self.required,
                "additionalProperties": False,
            },
        }


class Weft(BaseModel):
    """Represents a streaming semantic token interceptor / attunement declared by a yarn."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    pattern: re.Pattern
    description: str
    strip: bool = True
    priority: int = 100
    handler: Callable[..., Any] | None = None
    raw_handler: Callable[..., Any] | None = None
    args_schema: type[BaseModel] | None = None
    param_names: list[str] = Field(default_factory=list)

    def execute_match(self, match: re.Match) -> Any:
        """Execute weft attunement handler with regex match extracted arguments coerced with Pydantic."""
        raw_kwargs: dict[str, Any] = {}
        if named := {k: v for k, v in match.groupdict().items() if v is not None}:
            raw_kwargs = named
        elif match.groups():
            raw_kwargs = dict(zip(self.param_names, match.groups(), strict=False))
        elif len(self.param_names) == 1:
            raw_kwargs = {self.param_names[0]: match[0]}

        if self.args_schema:
            try:
                validated = self.args_schema.model_validate(raw_kwargs)
                coerced = validated.model_dump()
            except ValidationError as e:
                logger.warning(f"Weft '{self.name}' argument coercion failed: {e}")
                coerced = raw_kwargs
        else:
            coerced = raw_kwargs

        return self.handler(**coerced) if self.handler else None
