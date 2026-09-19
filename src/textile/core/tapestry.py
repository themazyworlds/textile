"""
Textile Tapestry - Core Task Ledger & Open Sensory Blackboard.
"""

import threading
from collections import deque
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class NoticeLevel(str, Enum):
    """Notice and Alert priority levels for the Sensory Tapestry Blackboard."""
    INFO = "INFO"
    NOTICE = "NOTICE"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class Notice(BaseModel):
    """A structured sensory/system notice stitched into Sensory Tapestry."""
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    level: NoticeLevel = NoticeLevel.INFO
    source: str
    message: str
    data: dict[str, Any] = Field(default_factory=dict)


class TaskRecord(BaseModel):
    """Engine task execution tracking."""
    task_id: str
    strand_name: str
    start_time: str
    args: dict[str, Any] = Field(default_factory=dict)
    duration_ms: float | None = None
    success: bool | None = None
    error: str | None = None


class CoreTapestry:
    """
    Core Task Ledger: Strictly manages engine execution, active strand tasks,
    runtime execution history, and task cancellation.
    """

    def __init__(self, max_history: int = 50):
        self._max_history = max_history
        self._lock = threading.Lock()
        self._active_tasks: dict[str, TaskRecord] = {}
        self._task_history: deque[TaskRecord] = deque(maxlen=max_history)

    def record_task_start(self, task_id: str, strand_name: str, args: dict[str, Any] | None = None) -> TaskRecord:
        record = TaskRecord(
            task_id=task_id,
            strand_name=strand_name,
            start_time=datetime.now(UTC).isoformat(),
            args=args or {},
        )
        with self._lock:
            self._active_tasks[task_id] = record
        return record

    def record_task_end(
        self,
        task_id: str,
        success: bool = True,
        duration_ms: float = 0.0,
        error: str | None = None,
    ) -> TaskRecord | None:
        with self._lock:
            record = self._active_tasks.pop(task_id, None)
            if record:
                record.success = success
                record.duration_ms = duration_ms
                record.error = error
                self._task_history.append(record)
        return record

    def cancel_task(self, identifier: str) -> str:
        clean_id = identifier.strip()
        if not clean_id:
            return "Error: No task identifier or strand name specified to cancel."

        with self._lock:
            for tid, task in list(self._active_tasks.items()):
                if tid == clean_id or task.strand_name == clean_id:
                    self._active_tasks.pop(tid, None)
                    return f"Successfully cancelled active task '{task.strand_name}' (ID: {tid})."
        return f"No active task matching '{clean_id}' currently running."

    def get_active_tasks(self) -> list[dict[str, Any]]:
        with self._lock:
            return [t.model_dump() for t in self._active_tasks.values()]

    def get_task_history(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            items = list(self._task_history)
        return [t.model_dump() for t in items[-limit:]]

    def get_state(self) -> dict[str, Any]:
        """Return snapshot of running engine tasks and recent execution history."""
        return {
            "active_tasks": self.get_active_tasks(),
            "task_history": self.get_task_history(limit=20),
        }


class SensoryTapestry:
    """
    Open Sensory Blackboard: Retained state slots and stitched alert/notice feed
    accessible to all yarns, plugins, and daemons.
    """

    def __init__(self, max_notices: int = 100):
        self._max_notices = max_notices
        self._lock = threading.Lock()
        self._slots: dict[str, Any] = {}
        self._notices: deque[Notice] = deque(maxlen=max_notices)

    def stitch(
        self,
        level: str | NoticeLevel,
        source: str,
        message: str,
        data: dict[str, Any] | None = None,
    ) -> Notice:
        """Stitch a structured notice or alert into the sensory Tapestry blackboard."""
        if isinstance(level, str):
            try:
                lvl = NoticeLevel(level.upper().strip())
            except ValueError:
                lvl = NoticeLevel.INFO
        else:
            lvl = level

        notice = Notice(
            level=lvl,
            source=str(source).strip(),
            message=str(message).strip(),
            data=data or {},
        )
        with self._lock:
            self._notices.append(notice)

        # Broadcast simultaneously to Warp for real-time streaming listeners
        try:
            from textile.core.warp import warp
            warp.publish(f"tapestry.{lvl.value.lower()}", notice.model_dump())
        except Exception:
            pass

        return notice

    def bind(
        self,
        level: str | NoticeLevel,
        source: str,
        message: str,
        data: dict[str, Any] | None = None,
    ) -> Notice:
        """Alias for stitch()."""
        return self.stitch(level, source, message, data)

    def set_slot(self, key: str, value: Any) -> None:
        """Set a retained state slot in the sensory blackboard."""
        with self._lock:
            self._slots[str(key).strip()] = value

    def get_slot(self, key: str, default: Any = None) -> Any:
        """Get a retained state slot value."""
        with self._lock:
            return self._slots.get(str(key).strip(), default)

    def get_notices(
        self,
        level: str | NoticeLevel | None = None,
        source: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Retrieve recent notices with optional level and source filtering."""
        target_lvl: NoticeLevel | None = None
        if level:
            if isinstance(level, str):
                try:
                    target_lvl = NoticeLevel(level.upper().strip())
                except ValueError:
                    target_lvl = None
            else:
                target_lvl = level

        with self._lock:
            items = list(self._notices)

        filtered = []
        for n in items:
            if target_lvl and n.level != target_lvl:
                continue
            if source and n.source.lower() != str(source).lower().strip():
                continue
            filtered.append(n.model_dump())
        return filtered[-limit:]

    def get_state(self) -> dict[str, Any]:
        """Return snapshot of sensory state slots and recent stitched notices."""
        with self._lock:
            slots_copy = dict(self._slots)
        return {
            "slots": slots_copy,
            "recent_notices": self.get_notices(limit=20),
        }


# Singletons
core_tapestry = CoreTapestry()
sensory_tapestry = SensoryTapestry()

# Backward-compatibility alias
tapestry = sensory_tapestry

