"""
Textile Execution Functional Domain Package.
Provides Yarn abstract base class, Strand models, Strand decorators,
invoker factory, and isolated subprocess runner.
"""

from textile.core.execution.validation import validate_strand_arguments
lazy from textile.core.definitions.errors import STRAND_EXEC_ERRORS
lazy from textile.core.execution.invoker import InvokerConfig, execute_direct
lazy from textile.core.execution.reflector import (
    bind_strand_to_core,
    method_to_strand,
    reflect_strands,
)
lazy from textile.core.execution.runner import execute_strand

__all__ = [
    "InvokerConfig",
    "STRAND_EXEC_ERRORS",
    "bind_strand_to_core",
    "execute_direct",
    "execute_strand",
    "method_to_strand",
    "reflect_strands",
    "validate_strand_arguments",
]
