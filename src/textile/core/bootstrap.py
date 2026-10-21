"""
Textile Engine AutoLoad Bootstrapper.
Loads declared engine subsystems into memory so their @camshaft.on
decorators register on the Camshaft event bus.
"""

import importlib

# Declared subsystem modules to boot into memory (like Godot's AutoLoads)
AUTOLOAD_SUBSYSTEMS: tuple[str, ...] = (
    "textile.core.loom.policy",
    "textile.core.loom.context",
    "textile.core.loom.mesh",
    "textile.core.skein.discovery",
    "textile.core.skein.mesh",
    "textile.core.fabric",
    "textile.core.tapestry.intra.mesh",
    "textile.core.tapestry.sensory.mesh",
    "textile.core.tapestry.elastic",
    "textile.core.twill.instructions",
    "textile.core.twill.mesh",
)


class _BootState:
    booted: bool = False


def bootstrap() -> None:
    """Boot all declared engine subsystems into memory."""
    if _BootState.booted:
        return
    _BootState.booted = True

    for module_path in AUTOLOAD_SUBSYSTEMS:
        importlib.import_module(module_path)


__all__ = ["AUTOLOAD_SUBSYSTEMS", "bootstrap"]
