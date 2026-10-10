"""
Textile Telemetry Functional Domain Package.
Provides sensory blackboard & task ledger (Tapestry) and cross-process event bus (Elastic).
"""

from typing import TYPE_CHECKING, Any

from textile.core.definitions.events import EventUrgency
from textile.core.telemetry.log import configure_logging, get_logger

if TYPE_CHECKING:
    from textile.core.telemetry.blackboard import (
        SensoryTapestry,
        sensory_tapestry,
    )
    from textile.core.telemetry.database import TapestryDatabase
    from textile.core.telemetry.elastic import ElasticEngine, EventFrame, elastic
    from textile.core.telemetry.ledger import (
        CoreTapestry,
        core_tapestry,
    )

_LAZY_EXPORTS = {
    "SensoryTapestry": ("textile.core.telemetry.blackboard", "SensoryTapestry"),
    "sensory_tapestry": ("textile.core.telemetry.blackboard", "sensory_tapestry"),
    "TapestryDatabase": ("textile.core.telemetry.database", "TapestryDatabase"),
    "ElasticEngine": ("textile.core.telemetry.elastic", "ElasticEngine"),
    "elastic": ("textile.core.telemetry.elastic", "elastic"),
    "EventFrame": ("textile.core.telemetry.elastic", "EventFrame"),
    "CoreTapestry": ("textile.core.telemetry.ledger", "CoreTapestry"),
    "core_tapestry": ("textile.core.telemetry.ledger", "core_tapestry"),
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
    "CoreTapestry",
    "ElasticEngine",
    "EventFrame",
    "EventUrgency",
    "SensoryTapestry",
    "TapestryDatabase",
    "configure_logging",
    "core_tapestry",
    "elastic",
    "get_logger",
    "sensory_tapestry",
]
