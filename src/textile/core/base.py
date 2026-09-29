"""
Textile Core Base System Definitions & Interface Exports.
Aggregates and re-exports core yarn, strand, manifest, and validation definitions.
"""

from textile.core.decorators import _parse_tier, strand, weft
from textile.core.manifest import (
    LAYER_BASE,
    LAYER_COMPOSITOR_DE,
    LAYER_DESKTOP_PROTOCOL,
    LAYER_SESSION_MANAGER,
    LAYER_USER_OVERRIDE,
    DependenciesManifest,
    YarnManifest,
)
from textile.core.strands import CapabilityTier, Strand, Weft
from textile.core.sys_detect import detect_shell, detect_terminal, detect_terminal_and_shell
from textile.core.validation import (
    _extract_docstring_info,
    detects_native_ffi,
    schema_to_model,
    validate_strand_arguments,
    validate_strand_schema,
)
from textile.core.yarn import (
    STRAND_EXEC_ERRORS,
    Yarn,
    _create_invoker,
    _exec_async_strand,
    _exec_sync_strand,
)

__all__ = [
    "LAYER_BASE",
    "LAYER_COMPOSITOR_DE",
    "LAYER_DESKTOP_PROTOCOL",
    "LAYER_SESSION_MANAGER",
    "LAYER_USER_OVERRIDE",
    "STRAND_EXEC_ERRORS",
    "CapabilityTier",
    "DependenciesManifest",
    "Strand",
    "Weft",
    "Yarn",
    "YarnManifest",
    "_create_invoker",
    "_exec_async_strand",
    "_exec_sync_strand",
    "_extract_docstring_info",
    "_parse_tier",
    "detect_shell",
    "detect_terminal",
    "detect_terminal_and_shell",
    "detects_native_ffi",
    "schema_to_model",
    "strand",
    "validate_strand_arguments",
    "validate_strand_schema",
    "weft",
]
