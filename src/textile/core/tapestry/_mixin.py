"""
Textile Tapestry Coordinator Mixin & Signals.
Unifies telemetry querying, persistent task ledgers, blackboard slot retention, and event broadcasting.
"""

from typing import Any

lazy import blinker

lazy from textile.core.bus import bus, emit
lazy from textile.core.tapestry.elastic import EventUrgency, elastic
lazy from textile.core.tapestry.intra import intra_mesh as core_tapestry
lazy from textile.core.tapestry.sensory import sensory_mesh as sensory_tapestry


class TapestryMixin:
    """Mixin providing telemetry, blackboard, and task ledger coordinator methods for Camshaft."""

    class TapestrySignals:
        blackboard_slot_input: blinker.Signal = bus.signal("blackboard:slot_input")
        blackboard_slot_updated: blinker.Signal = bus.signal("blackboard:slot_updated")
        stitch_notice: blinker.Signal = bus.signal("telemetry:stitch_notice")

    @staticmethod
    def get_engine_state() -> dict[str, Any]:
        """Return snapshot of running engine tasks and recent execution history."""
        return core_tapestry.get_engine_state()

    @staticmethod
    def get_sensory_state() -> dict[str, Any]:
        """Return snapshot of sensory state slots and recent stitched notices."""
        return sensory_tapestry.get_state()

    @staticmethod
    def get_active_tasks() -> list[dict[str, Any]]:
        """List all currently running engine tasks."""
        return core_tapestry.get_active_tasks()

    @staticmethod
    def get_task_history(limit: int = 50) -> list[dict[str, Any]]:
        """Retrieve recent task execution history records."""
        return core_tapestry.get_task_history(limit=limit)

    @staticmethod
    def cancel_task(identifier: str) -> str:
        """Cancel an active task by task ID or strand name."""
        return core_tapestry.cancel_task(identifier)

    @staticmethod
    def set_blackboard_slot(key: str, value: Any) -> None:
        """Set a retained state slot in the sensory blackboard via input event."""
        emit(TapestryMixin.TapestrySignals.blackboard_slot_input, key=key, value=value)

    @staticmethod
    def get_blackboard_slot(key: str, default: Any = None) -> Any:
        """Retrieve a retained state slot from the sensory blackboard."""
        return sensory_tapestry.get_slot(key, default=default)

    @staticmethod
    def stitch_notice(
        level: str,
        source: str,
        message: str,
        data: dict[str, Any] | None = None,
    ) -> None:
        """Stitch a structured notice or alert into the sensory blackboard."""
        emit(TapestryMixin.TapestrySignals.stitch_notice, level=level, source=source, message=message, data=data)

    @staticmethod
    def broadcast_telemetry(  # noqa: PLR0913
        topic: str,
        summary: str,
        *,
        source: str = "textile",
        urgency: str = "AMBIENT",
        data: dict[str, Any] | None = None,
        retained_slot: str | None = None,
        retained_value: Any = None,
    ) -> None:
        """Broadcast a real-time event through the telemetry stream."""
        urg = EventUrgency.from_value(urgency)
        elastic.broadcast(
            topic=topic,
            source=source,
            summary=summary,
            urgency=urg,
            data=data,
            retained_slot=retained_slot,
            retained_value=retained_value,
        )


__all__ = ["TapestryMixin"]
