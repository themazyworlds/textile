"""
Textile Event Definitions & Urgency Tiers.
Provides pure enum and data structures for event publication without engine dependencies.
"""

from enum import StrEnum
from typing import Any


class EventUrgency(StrEnum):
    """Urgency / Priority tiers for Elastic events."""

    AMBIENT = "ambient"  # Background telemetry, periodic status (urgency ~0.1)
    NOTICE = "notice"  # Standard state changes, task completion, info (urgency ~0.3)
    ALERT = "alert"  # High priority alerts, warnings, tension sparks (urgency ~0.7)
    FLASH = "flash"  # Critical errors, crashes, immediate emergency (urgency 1.0)

    @property
    def numeric(self) -> float:
        mapping = {
            EventUrgency.AMBIENT: 0.1,
            EventUrgency.NOTICE: 0.3,
            EventUrgency.ALERT: 0.7,
            EventUrgency.FLASH: 1.0,
        }
        return mapping.get(self, 0.3)

    @classmethod
    def from_value(cls, val: Any) -> EventUrgency:
        if isinstance(val, EventUrgency):
            return val
        s = str(val or "").lower().strip()
        if s in {"flash", "crit", "critical", "emerg", "emergency", "1.0", "1"}:
            return EventUrgency.FLASH
        if s in {"alert", "warning", "warn", "0.7", "0.8", "0.9"}:
            return EventUrgency.ALERT
        if s in {"ambient", "debug", "trace", "0.1", "0.2"}:
            return EventUrgency.AMBIENT
        return EventUrgency.NOTICE
