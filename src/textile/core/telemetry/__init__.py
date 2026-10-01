"""
Textile Telemetry Functional Domain Package.
Provides sensory blackboard & task ledger (Tapestry), cross-process event bus (Elastic),
integrity auditing (Seams), and undo stack (Transaction).
"""

from textile.core.telemetry.auditor import audit_all, audit_strand, audit_yarn
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
from textile.core.telemetry.seams import SeamOrchestrator, seams
from textile.core.telemetry.transaction import Transaction, transaction_stack

__all__ = [
    "CoreTapestry",
    "ElasticEngine",
    "EventFrame",
    "EventUrgency",
    "SeamOrchestrator",
    "SensoryTapestry",
    "TapestryDatabase",
    "Transaction",
    "audit_all",
    "audit_strand",
    "audit_yarn",
    "configure_logging",
    "core_tapestry",
    "elastic",
    "get_logger",
    "seams",
    "sensory_tapestry",
    "transaction_stack",
]
