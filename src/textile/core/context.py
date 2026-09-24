"""
Textile Core Layer 1 - Context & Biometric Seat Engine.
Defines origin token authentication, trust levels, and local seat verification.
"""

import os
import time
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field


class OriginType(StrEnum):
    """Classification of intent input origin."""
    LOCAL_VOICE = "local_voice"            # Local microphone audio voice stream (High Trust)
    LOCAL_SEAT = "local_seat"              # Local keyboard/UI shortcut or terminal (High Trust)
    SYSTEM_INTERNAL = "system_internal"    # Native Textile system event or Warp bus (Medium Trust)
    EXTERNAL_UNTRUSTED = "external_untrusted" # Web scraping, external files, email, network payloads (Zero Trust)


class TrustLevel(StrEnum):
    """Calculated trust tier of an intent origin."""
    HIGH = "high"       # Full autonomous execution of observe, interact, and mutate strands
    MEDIUM = "medium"   # Execution of observe and interact strands
    LOW = "low"         # Observe-only strands
    NONE = "none"       # Zero execution power (rejection of all mutative/privileged strands)


class OriginToken(BaseModel):
    """Cryptographic/session token representing the source and trust of an intent.

    Frozen: trust_level and origin_type cannot be mutated after creation.
    An attacker must never be able to escalate their own trust in memory.
    """

    model_config = ConfigDict(frozen=True)

    origin_id: str
    origin_type: OriginType
    trust_level: TrustLevel = TrustLevel.HIGH
    timestamp: float = Field(default_factory=time.time)
    metadata: dict[str, Any] = Field(default_factory=dict)
    tainted: bool = False
    taint_source: str | None = None

    def taint(self, source: str) -> Self:
        """Derive an untrusted child token from tainted external data.

        Prevents Confused Deputy and indirect prompt injection attacks by
        downgrading trust_level to NONE whenever external data influences the intent.
        """
        return self.__class__(
            origin_id=f"{self.origin_id}::tainted({source})",
            origin_type=OriginType.EXTERNAL_UNTRUSTED,
            trust_level=TrustLevel.NONE,
            timestamp=time.time(),
            metadata={**self.metadata, "tainted": True, "taint_source": source},
            tainted=True,
            taint_source=source,
        )

    @classmethod
    def create_local_voice(cls, session_id: str = "local_voice") -> Self:
        return cls(
            origin_id=session_id,
            origin_type=OriginType.LOCAL_VOICE,
            trust_level=TrustLevel.HIGH,
            metadata={"uid": os.getuid()},
        )

    @classmethod
    def create_local_seat(cls, seat_id: str = "local_seat") -> Self:
        seat = SeatContext()
        if not seat.is_authenticated_local_user():
            raise PermissionError(
                f"Cannot create LOCAL_SEAT origin token: no authenticated local display session detected "
                f"(uid={seat.uid}, display={seat.display})."
            )
        return cls(
            origin_id=seat_id,
            origin_type=OriginType.LOCAL_SEAT,
            trust_level=TrustLevel.HIGH,
            metadata={"uid": seat.uid, "display": seat.display},
        )

    @classmethod
    def create_external_untrusted(cls, source_uri: str) -> Self:
        return cls(
            origin_id=source_uri,
            origin_type=OriginType.EXTERNAL_UNTRUSTED,
            trust_level=TrustLevel.NONE,
            metadata={"uri": source_uri},
            tainted=True,
            taint_source=source_uri,
        )


class TaintTracker:
    """Ambient data flow taint tracker across LLM reasoning loops."""

    _active_taint: str | None = None

    @classmethod
    def set_taint(cls, source: str) -> None:
        cls._active_taint = source

    @classmethod
    def clear_taint(cls) -> None:
        cls._active_taint = None

    @classmethod
    def get_taint(cls) -> str | None:
        return cls._active_taint

    @classmethod
    def is_tainted(cls) -> bool:
        return cls._active_taint is not None



@dataclass
class SeatContext:
    """Verifies physical presence and local desktop ownership."""

    uid: int = field(default_factory=os.getuid)
    display: str | None = field(default_factory=lambda: os.environ.get("WAYLAND_DISPLAY") or os.environ.get("DISPLAY"))

    def is_authenticated_local_user(self) -> bool:
        return self.uid == os.getuid() and self.display is not None


class PolicyViolationError(PermissionError):
    """Raised when an operation violates Layer 1/3 security policy matrix."""
    pass


ALLOWED_TIERS: dict[TrustLevel, set[str]] = {
    TrustLevel.HIGH: {"observe", "interact", "mutate", "privileged", "system_exec"},
    TrustLevel.MEDIUM: {"observe", "interact"},
    TrustLevel.LOW: {"observe"},
    TrustLevel.NONE: {"observe"},
}


def verify_security_policy(
    token: OriginToken,
    tier: Any,
    strand_name: str,
) -> None:
    """Canonical single-source-of-truth security policy gate.

    Verifies caller's OriginToken trust level against the strand's capability tier.
    Raises PolicyViolationError if execution is denied.
    """
    trust = token.trust_level
    tier_val = tier.value if hasattr(tier, "value") else str(tier).lower()

    allowed_tiers = ALLOWED_TIERS.get(trust, set())
    if tier_val not in allowed_tiers:
        raise PolicyViolationError(
            f"Security Policy Violation: Origin '{token.origin_id}' (trust={trust}) "
            f"is denied execution of '{tier_val}' strand '{strand_name}'."
        )


