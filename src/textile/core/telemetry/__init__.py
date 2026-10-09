"""
Textile Telemetry Functional Domain Package.
Provides sensory blackboard & task ledger (Tapestry) and cross-process event bus (Elastic).
"""

from textile.core.telemetry.blackboard import (
    SensoryTapestry,
    sensory_tapestry,
)
from textile.core.telemetry.database import TapestryDatabase
from textile.core.telemetry.elastic import ElasticEngine, EventFrame, EventUrgency, elastic
from textile.core.telemetry.ledger import (
    CoreTapestry,
    core_tapestry,
)
from textile.core.telemetry.log import configure_logging, get_logger

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
