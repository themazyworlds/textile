"""
Textile Core Layer 1 - Context & Biometric Seat Engine.
Defines origin token authentication, trust levels, and local seat verification.
"""

import os
import time
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Self

from pydantic import BaseModel, Field


class OriginType(StrEnum):
    """Classification of intent input origin."""
    LOCAL_VOICE = "local_voice"            # LiveKit local microphone voice stream (High Trust)
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
    """Cryptographic/session token representing the source and trust of an intent."""

    origin_id: str
    origin_type: OriginType
    trust_level: TrustLevel = TrustLevel.HIGH
    timestamp: float = Field(default_factory=time.time)
    metadata: dict[str, Any] = Field(default_factory=dict)

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
        )


@dataclass
class SeatContext:
    """Verifies physical presence and local desktop ownership."""

    uid: int = field(default_factory=os.getuid)
    display: str | None = field(default_factory=lambda: os.environ.get("WAYLAND_DISPLAY") or os.environ.get("DISPLAY"))

    def is_authenticated_local_user(self) -> bool:
        return self.uid == os.getuid() and self.display is not None
