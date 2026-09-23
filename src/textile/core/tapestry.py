"""
Textile Tapestry - Core Task Ledger & Open Sensory Blackboard.
"""

import json
import logging
import os
import tempfile
import threading
from collections import deque
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from textile.core.warp import warp

logger = logging.getLogger(__name__)


class NoticeLevel(StrEnum):
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
    tier: str | None = None
    trust_level: str | None = None
    tainted: bool = False


def _get_runtime_dir() -> Path:
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    p = Path(runtime) / "textile" if runtime else Path(tempfile.gettempdir()) / f"textile-{os.getuid()}"
    p.mkdir(parents=True, exist_ok=True)
    return p


class CoreTapestry:
    """
    Core Task Ledger: Strictly manages engine execution, active strand tasks,
    runtime execution history, and task cancellation.
    Synchronizes state across processes via tmpfs shared runtime directory.
    """

    def __init__(self, max_history: int = 50, persist: bool = False):
        self._max_history = max_history
        self._persist = persist
        self._lock = threading.Lock()
        self._active_tasks: dict[str, TaskRecord] = {}
        self._task_history: deque[TaskRecord] = deque(maxlen=max_history)

    def _sync_to_disk(self) -> None:
        if not self._persist:
            return
        try:
            rdir = _get_runtime_dir()
            target = rdir / "tasks.json"
            tmp = rdir / "tasks.json.tmp"
            data = {
                "active_tasks": {tid: t.model_dump() for tid, t in self._active_tasks.items()},
                "task_history": [t.model_dump() for t in self._task_history],
            }
            tmp.write_text(json.dumps(data), encoding="utf-8")
            tmp.replace(target)
        except (OSError, TypeError, ValueError) as e:
            logger.debug("Error syncing CoreTapestry: %s", e)

    def _load_from_disk(self) -> None:
        if not self._persist:
            return
        try:
            target = _get_runtime_dir() / "tasks.json"
            if target.exists():
                data = json.loads(target.read_text(encoding="utf-8"))
                loaded_active = {}
                for tid, tdict in data.get("active_tasks", {}).items():
                    loaded_active[tid] = TaskRecord(**tdict)
                self._active_tasks = loaded_active

                loaded_history = deque(maxlen=self._max_history)
                for tdict in data.get("task_history", []):
                    loaded_history.append(TaskRecord(**tdict))
                self._task_history = loaded_history
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as e:
            logger.debug("Error loading CoreTapestry: %s", e)

    def record_task_start(
        self,
        task_id: str,
        strand_name: str,
        args: dict[str, Any] | None = None,
        tier: str | None = None,
        trust_level: str | None = None,
        tainted: bool = False,
    ) -> TaskRecord:
        record = TaskRecord(
            task_id=task_id,
            strand_name=strand_name,
            start_time=datetime.now(UTC).isoformat(),
            args=args or {},
            tier=tier,
            trust_level=trust_level,
            tainted=tainted,
        )
        with self._lock:
            self._load_from_disk()
            self._active_tasks[task_id] = record
            self._sync_to_disk()
        return record

    def record_task_end(
        self,
        task_id: str,
        success: bool = True,
        duration_ms: float = 0.0,
        error: str | None = None,
    ) -> TaskRecord | None:
        with self._lock:
            self._load_from_disk()
            record = self._active_tasks.pop(task_id, None)
            if record:
                record.success = success
                record.duration_ms = duration_ms
                record.error = error
                self._task_history.append(record)
                self._sync_to_disk()
        return record

    def cancel_task(self, identifier: str) -> str:
        clean_id = identifier.strip()
        if not clean_id:
            return "Error: No task identifier or strand name specified to cancel."

        with self._lock:
            self._load_from_disk()
            for tid, task in list(self._active_tasks.items()):
                if clean_id in (tid, task.strand_name):
                    self._active_tasks.pop(tid, None)
                    self._sync_to_disk()
                    return f"Successfully cancelled active task '{task.strand_name}' (ID: {tid})."
        return f"No active task matching '{clean_id}' currently running."

    def get_active_tasks(self) -> list[dict[str, Any]]:
        with self._lock:
            self._load_from_disk()
            return [t.model_dump() for t in self._active_tasks.values()]

    def get_task_history(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            self._load_from_disk()
            items = list(self._task_history)
        return [t.model_dump() for t in items[-limit:]]

    def clear(self) -> None:
        """Clear active tasks and execution history."""
        with self._lock:
            self._active_tasks.clear()
            self._task_history.clear()
            if self._persist:
                self._sync_to_disk()

    def get_state(self) -> dict[str, Any]:
        """Return snapshot of running engine tasks and recent execution history."""
        return {
            "active_tasks": self.get_active_tasks(),
            "task_history": self.get_task_history(limit=20),
        }


class SensoryTapestry:
    """
    Open Sensory Blackboard: Retained state slots and stitched alert/notice feed
    accessible to all yarns, plugins, and daemons across processes.
    """

    def __init__(self, max_notices: int = 100, persist: bool = False):
        self._max_notices = max_notices
        self._persist = persist
        self._lock = threading.Lock()
        self._slots: dict[str, Any] = {}
        self._notices: deque[Notice] = deque(maxlen=max_notices)

    def _sync_to_disk(self) -> None:
        if not self._persist:
            return
        try:
            rdir = _get_runtime_dir()
            target = rdir / "sensory.json"
            tmp = rdir / "sensory.json.tmp"
            data = {
                "slots": self._slots,
                "notices": [n.model_dump() for n in self._notices],
            }
            tmp.write_text(json.dumps(data), encoding="utf-8")
            tmp.replace(target)
        except (OSError, TypeError, ValueError) as e:
            logger.debug("Error syncing SensoryTapestry: %s", e)

    def _load_from_disk(self) -> None:
        if not self._persist:
            return
        try:
            target = _get_runtime_dir() / "sensory.json"
            if target.exists():
                data = json.loads(target.read_text(encoding="utf-8"))
                for k, v in data.get("slots", {}).items():
                    self._slots[k] = v
                loaded_notices = deque(maxlen=self._max_notices)
                for ndict in data.get("notices", []):
                    loaded_notices.append(Notice(**ndict))
                self._notices = loaded_notices
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as e:
            logger.debug("Error loading SensoryTapestry: %s", e)

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
            self._load_from_disk()
            self._notices.append(notice)
            self._sync_to_disk()

        # Broadcast simultaneously to Warp for real-time streaming listeners
        try:
            warp.publish(f"tapestry.{lvl.value.lower()}", notice.model_dump())
        except (AttributeError, TypeError, ValueError, KeyError, OSError, RuntimeError) as e:
            logger.warning("Failed to broadcast notice to Warp: %s", e)

        return notice

    def set_slot(self, key: str, value: Any) -> None:
        """Set a retained state slot in the sensory blackboard."""
        with self._lock:
            self._load_from_disk()
            self._slots[str(key).strip()] = value
            self._sync_to_disk()

    def get_slot(self, key: str, default: Any = None) -> Any:
        """Get a retained state slot value."""
        with self._lock:
            self._load_from_disk()
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
            self._load_from_disk()
            items = list(self._notices)

        filtered = []
        for n in items:
            if target_lvl and n.level != target_lvl:
                continue
            if source and n.source.lower() != str(source).lower().strip():
                continue
            filtered.append(n.model_dump())
        return filtered[-limit:]

    def clear(self) -> None:
        """Clear all sensory state slots and notices."""
        with self._lock:
            self._slots.clear()
            self._notices.clear()
            if self._persist:
                self._sync_to_disk()

    def get_state(self) -> dict[str, Any]:
        """Return snapshot of sensory state slots and recent stitched notices."""
        with self._lock:
            self._load_from_disk()
            slots_copy = dict(self._slots)
        return {
            "slots": slots_copy,
            "recent_notices": self.get_notices(limit=20),
        }


# Global Shared Singletons (persisted to runtime tmpfs for cross-process IPC)
core_tapestry = CoreTapestry(persist=True)
sensory_tapestry = SensoryTapestry(persist=True)


