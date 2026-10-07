"""
Textile Sandbox Confinement Subsystem Package.
Provides Bubblewrap (bwrap) unprivileged container isolation, Landlock kernel walls,
and declarative IPC desktop resource resolution inspired by Bubblejail architecture.
"""

from textile.core.security.sandbox.bwrap import BubblewrapBuilder, BubblewrapSandbox
from textile.core.security.sandbox.landlock import LandlockSandbox
from textile.core.security.sandbox.resources import resolve_sandbox_resources

__all__ = [
    "BubblewrapBuilder",
    "BubblewrapSandbox",
    "LandlockSandbox",
    "resolve_sandbox_resources",
]
