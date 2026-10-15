"""
Execution telemetry dispatcher for task tracking, blackboard stitching, and event broadcasting.
"""

from dataclasses import dataclass
from typing import Any

from textile.core.telemetry.blackboard import NoticeLevel, sensory_tapestry
from textile.core.telemetry.elastic import EventUrgency, elastic
from textile.core.telemetry.ledger import core_tapestry

__all__ = ["ExecutionTelemetryContext", "record_execution_end", "record_execution_start"]


@dataclass(slots=True)
class ExecutionTelemetryContext:
    task_id: str
    strand_name: str
    args: dict[str, Any]
    tier_val: str
    caller: str


def record_execution_start(ctx: ExecutionTelemetryContext) -> None:
    """Record task start telemetry in CoreTapestry and Elastic."""
    core_tapestry.record_task_start(
        ctx.task_id,
        ctx.strand_name,
        args=ctx.args,
        tier=ctx.tier_val,
    )
    elastic.broadcast(
        topic="loom.tool_start",
        source="loom",
        summary=f"Starting strand '{ctx.strand_name}' [{ctx.tier_val.upper()}]",
        urgency=EventUrgency.AMBIENT,
        data={"task_id": ctx.task_id, "strand": ctx.strand_name, "caller": ctx.caller, "tier": ctx.tier_val},
    )


def record_execution_end(
    ctx: ExecutionTelemetryContext,
    dur_ms: float,
    success: bool,
    err: str | None,
) -> None:
    """Record task completion telemetry in CoreTapestry, SensoryTapestry, and Elastic."""
    core_tapestry.record_task_end(ctx.task_id, success=success, duration_ms=dur_ms, error=err)
    msg = (
        f"Executed '{ctx.strand_name}' [{ctx.tier_val.upper()}] ({dur_ms:.1f}ms)"
        if success
        else f"Failed '{ctx.strand_name}': {err}"
    )
    sensory_tapestry.stitch(
        level=NoticeLevel.INFO if success else NoticeLevel.ERROR,
        source=ctx.strand_name,
        message=msg,
        data={
            "caller": ctx.caller,
            "args": ctx.args,
            "tier": ctx.tier_val,
        },
    )
    elastic.broadcast(
        topic="loom.tool_done",
        source="loom",
        summary=msg,
        urgency=EventUrgency.NOTICE if success else EventUrgency.ALERT,
        data={
            "task_id": ctx.task_id,
            "strand": ctx.strand_name,
            "success": success,
            "duration_ms": dur_ms,
            "caller": ctx.caller,
            "error": err,
        },
    )
