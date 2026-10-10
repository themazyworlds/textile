"""
Textile Execution Functional Domain Package.
Provides Yarn abstract base class, Strand & Weft models, Strand decorators,
invoker factory, and isolated subprocess runner.
"""

from typing import TYPE_CHECKING, Any

from textile.core.execution.decorators import strand, weft
from textile.core.execution.strands import CapabilityTier, Strand, Weft
from textile.core.execution.validation import validate_strand_arguments
from textile.core.execution.yarn import EventOptions, StrandConfig, Yarn

if TYPE_CHECKING:
    from textile.core.execution.invoker import InvokerConfig, _build_args_model, _create_invoker
    from textile.core.execution.isolated_runner import execute_isolated_strand

_LAZY_EXPORTS = {
    "InvokerConfig": ("textile.core.execution.invoker", "InvokerConfig"),
    "_build_args_model": ("textile.core.execution.invoker", "_build_args_model"),
    "_create_invoker": ("textile.core.execution.invoker", "_create_invoker"),
    "execute_isolated_strand": ("textile.core.execution.isolated_runner", "execute_isolated_strand"),
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
    "execute_isolated_strand",
    "strand",
    "validate_strand_arguments",
    "weft",
]
