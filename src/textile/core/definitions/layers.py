"""
Textile Core Layer Hierarchy, Priority Thresholds, and Override Resolution Engine.
Defines fabric execution layers from Core POSIX (Layer 10) up to User Override (Layer 1000).
"""

from dataclasses import dataclass
from enum import IntEnum
from typing import Any


class LayerTier(IntEnum):
    """Standard fabric priority layer tiers."""

    CORE_POSIX = 10
    DESKTOP_PROTOCOL = 50
    COMPOSITOR_DE = 100
    SESSION_MANAGER = 150
    USER_OVERRIDE = 1000


LAYER_USER_OVERRIDE_THRESHOLD = LayerTier.USER_OVERRIDE.value
LAYER_SESSION_MANAGER_THRESHOLD = LayerTier.SESSION_MANAGER.value
LAYER_COMPOSITOR_DE_THRESHOLD = LayerTier.COMPOSITOR_DE.value
LAYER_DESKTOP_PROTOCOL_THRESHOLD = LayerTier.DESKTOP_PROTOCOL.value
LAYER_CORE_POSIX_THRESHOLD = LayerTier.CORE_POSIX.value


@dataclass(frozen=True)
class LayerInfo:
    """Represents layer hierarchy metadata for a given numeric priority layer."""

    level: int
    name: str
    threshold: int

    def to_dict(self) -> dict[str, Any]:
        return {"level": self.level, "name": self.name}


def get_layer_info(layer: int) -> LayerInfo:
    """Resolve priority layer integer to layer hierarchy metadata."""
    if layer >= LAYER_USER_OVERRIDE_THRESHOLD:
        return LayerInfo(level=5, name="User Override", threshold=LAYER_USER_OVERRIDE_THRESHOLD)
    if layer >= LAYER_SESSION_MANAGER_THRESHOLD:
        return LayerInfo(level=4, name="Session Manager", threshold=LAYER_SESSION_MANAGER_THRESHOLD)
    if layer >= LAYER_COMPOSITOR_DE_THRESHOLD:
        return LayerInfo(level=3, name="Compositor / DE", threshold=LAYER_COMPOSITOR_DE_THRESHOLD)
    if layer >= LAYER_DESKTOP_PROTOCOL_THRESHOLD:
        return LayerInfo(level=2, name="Desktop Protocol", threshold=LAYER_DESKTOP_PROTOCOL_THRESHOLD)
    return LayerInfo(level=1, name="Core POSIX", threshold=LAYER_CORE_POSIX_THRESHOLD)
