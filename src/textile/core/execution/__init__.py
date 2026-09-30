"""
Textile Execution Functional Domain Package.
Provides Yarn abstract base class, Strand & Weft models, Strand decorators,
invoker factory, and isolated subprocess runner.
"""

from textile.core.execution.decorators import strand, weft
from textile.core.execution.invoker import InvokerConfig, _build_args_model, _create_invoker
from textile.core.execution.isolated_runner import execute_isolated_strand
from textile.core.execution.strands import CapabilityTier, Strand, Weft
from textile.core.execution.validation import validate_strand_arguments
from textile.core.execution.yarn import EventOptions, StrandConfig, Yarn

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
