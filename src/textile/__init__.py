"""
Textile • Sovereign AI Subsystem & Desktop Intelligence Engine.
"""

lazy from hem import SandboxUnavailableError
lazy from needle import (
    DEFAULT_LAYER,
    Strand,
    StrandCollisionError,
    StrandNotFoundError,
    StrandOperationalError,
    Yarn,
    YarnNotFoundError,
    strand,
)

__version__ = "0.1.0"

lazy from textile.core.camshaft import Camshaft, camshaft
lazy from textile.core.loom.mesh import loom
lazy from textile.core.skein.mesh import skein
lazy from textile.core.tapestry.elastic import EventFrame, EventUrgency, elastic
lazy from textile.core.tapestry.intra import core_tapestry, intra_mesh
lazy from textile.core.tapestry.sensory import sensory_mesh, sensory_tapestry
lazy from textile.core.twill.instructions import fabric_instructions

__all__ = [
    "Camshaft",
    "DEFAULT_LAYER",
    "EventFrame",
    "EventUrgency",
    "SandboxUnavailableError",
    "Strand",
    "StrandCollisionError",
    "StrandNotFoundError",
    "StrandOperationalError",
    "Yarn",
    "YarnNotFoundError",
    "__version__",
    "camshaft",
    "core_tapestry",
    "elastic",
    "fabric_instructions",
    "intra_mesh",
    "loom",
    "sensory_mesh",
    "sensory_tapestry",
    "skein",
    "strand",
]
