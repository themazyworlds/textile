"""
Textile Definitions Functional Domain Package.
Provides Intent DAG nodes, layer priority definitions,
error hierarchy, and system feature detection.
"""

from textile.core.definitions import shims
from textile.core.definitions.errors import (
    OTPChallengeRequiredError,
    PolicyViolationError,
    SandboxUnavailableError,
    StrandCollisionError,
    StrandNotFoundError,
    StrandOperationalError,
    TextileError,
    YarnNotFoundError,
)
from textile.core.definitions.layers import LayerTier, get_layer_info
from textile.core.execution.validation import detects_native_ffi

__all__ = [
    "LayerTier",
    "OTPChallengeRequiredError",
    "PolicyViolationError",
    "SandboxUnavailableError",
    "StrandCollisionError",
    "StrandNotFoundError",
    "StrandOperationalError",
    "TextileError",
    "YarnNotFoundError",
    "detects_native_ffi",
    "get_layer_info",
    "shims",
]
