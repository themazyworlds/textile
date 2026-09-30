"""
Textile Definitions Functional Domain Package.
Provides Yarn manifest TOML schema, Intent DAG nodes, layer priority definitions,
error hierarchy, and system feature detection.
"""

from textile.core.definitions.errors import (
    StrandNotFoundError,
    TextileError,
    YarnNotFoundError,
)
from textile.core.definitions.intent import IntentNode, IntentValidationError
from textile.core.definitions.layers import LayerTier, get_layer_info
from textile.core.definitions.manifest import DependenciesManifest, YarnManifest
from textile.core.execution.validation import detects_native_ffi
from textile.core.security.context import PolicyViolationError

__all__ = [
    "DependenciesManifest",
    "IntentNode",
    "IntentValidationError",
    "LayerTier",
    "PolicyViolationError",
    "StrandNotFoundError",
    "TextileError",
    "YarnManifest",
    "YarnNotFoundError",
    "detects_native_ffi",
    "get_layer_info",
]
