"""
Textile Telemetry Functional Domain Package.
Provides sensory blackboard & task ledger (Tapestry), cross-process event bus (Elastic),
integrity auditing (Seams), and undo stack (Transaction).
"""

from textile.core.telemetry.elastic import ElasticEngine, EventFrame, EventUrgency, elastic
from textile.core.telemetry.seams import SeamOrchestrator, seams
from textile.core.telemetry.tapestry import (
    CoreTapestry,
    SensoryTapestry,
    TapestryDB,
    core_tapestry,
    sensory_tapestry,
)
from textile.core.telemetry.transaction import Transaction, transaction_stack

__all__ = [
    "CoreTapestry",
    "ElasticEngine",
    "EventFrame",
    "EventUrgency",
    "SeamOrchestrator",
    "SensoryTapestry",
    "TapestryDB",
    "Transaction",
    "core_tapestry",
    "elastic",
    "seams",
    "sensory_tapestry",
    "transaction_stack",
]
