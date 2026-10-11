"""
Textile Execution Functional Domain Package.
Provides Yarn abstract base class, Strand & Weft models, Strand decorators,
invoker factory, and isolated subprocess runner.
"""

from typing import TYPE_CHECKING, Any

from needle import CapabilityTier, Strand, Weft, Yarn, strand, weft

from textile.core.definitions.events import EventOptions
from textile.core.execution.reflector import StrandConfig
from textile.core.execution.validation import validate_strand_arguments

if TYPE_CHECKING:
    from textile.core.execution.invoker import InvokerConfig, _build_args_model, _create_invoker
    from textile.core.execution.runner import execute_strand

_LAZY_EXPORTS = {
    "InvokerConfig": ("textile.core.execution.invoker", "InvokerConfig"),
    "_build_args_model": ("textile.core.execution.invoker", "_build_args_model"),
    "_create_invoker": ("textile.core.execution.invoker", "_create_invoker"),
    "execute_strand": ("textile.core.execution.runner", "execute_strand"),
}


def __getattr__(name: str) -> Any:
    if name in _LAZY_EXPORTS:
        module_path, attr_name = _LAZY_EXPORTS[name]
        module = __import__(module_path, fromlist=[attr_name])
        val = getattr(module, attr_name)
        globals()[name] = val
        return val
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


def __dir__() -> list[str]:
    return sorted(set(list(globals().keys()) + list(_LAZY_EXPORTS.keys()) + __all__))


__all__ = [
    "CapabilityTier",
    "EventOptions",
    "InvokerConfig",
    "Strand",
    "StrandConfig",
    "Weft",
    "Yarn",
    "_build_args_model",
    "_create_invoker",
    "execute_strand",
    "strand",
    "validate_strand_arguments",
    "weft",
]
