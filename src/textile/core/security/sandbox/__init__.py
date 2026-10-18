"""
Textile Sandbox Confinement Subsystem Package.
Provides Bubblewrap (bwrap) unprivileged container isolation,
and declarative IPC desktop resource resolution inspired by Bubblejail architecture.
"""

from hem import BubblewrapBuilder

from textile.core.security.sandbox.bwrap import (
    BubblewrapSandbox,
    create_sandbox_builder,
    is_sandbox_available,
    wrap_sandboxed_command,
)
from textile.core.security.sandbox.resources import apply_sandbox_resources

__all__ = [
    "BubblewrapBuilder",
    "BubblewrapSandbox",
    "apply_sandbox_resources",
    "create_sandbox_builder",
    "is_sandbox_available",
    "wrap_sandboxed_command",
]
