"""
Textile Tapestry - Core Task Ledger & Open Sensory Blackboard.
Uses SQLite WAL mode for high-speed, thread-safe, and process-safe IPC persistence.
"""

import contextlib
import json
import logging
import os
import sqlite3
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


def _get_db_path() -> Path:
    return _get_runtime_dir() / "tapestry.db"


def _init_db(conn: sqlite3.Connection) -> None:
    with conn:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS active_tasks (
                task_id TEXT PRIMARY KEY,
                strand_name TEXT NOT NULL,
                start_time TEXT NOT NULL,
                args_json TEXT,
                tier TEXT,
                trust_level TEXT,
                tainted INTEGER DEFAULT 0
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS task_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT,
                strand_name TEXT NOT NULL,
                start_time TEXT NOT NULL,
                duration_ms REAL,
                success INTEGER,
                error TEXT,
                tier TEXT,
                trust_level TEXT,
                tainted INTEGER DEFAULT 0,
                args_json TEXT
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS slots (
                key TEXT PRIMARY KEY,
                val_json TEXT
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS notices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                level TEXT NOT NULL,
                source TEXT NOT NULL,
                message TEXT NOT NULL,
                data_json TEXT
            );
        """)


def _get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(_get_db_path(), timeout=10.0)
    _init_db(conn)
    return conn


class CoreTapestry:
    """
    Core Task Ledger: Strictly manages engine execution, active strand tasks,
    runtime execution history, and task cancellation.
    Synchronizes state across processes via SQLite WAL mode in shared runtime directory.
    """

    def __init__(self, max_history: int = 50, persist: bool = False):
        self._max_history = max_history
        self._persist = persist
        self._lock = threading.RLock()
        self._active_tasks: dict[str, TaskRecord] = {}
        self._task_history: deque[TaskRecord] = deque(maxlen=max_history)

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
            self._active_tasks[task_id] = record
            if self._persist:
                try:
                    with _get_connection() as conn:
                        query = """
                            INSERT OR REPLACE INTO active_tasks
                            (task_id, strand_name, start_time, args_json, tier, trust_level, tainted)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                        """
                        conn.execute(
                            query,
                            (
                                record.task_id,
                                record.strand_name,
                                record.start_time,
                                json.dumps(record.args),
                                record.tier,
                                record.trust_level,
                                1 if record.tainted else 0,
                            ),
                        )
                except (sqlite3.Error, OSError) as e:
                    logger.debug("CoreTapestry DB error on start: %s", e)
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
            if not record and self._persist:
                try:
                    with _get_connection() as conn:
                        cur = conn.cursor()
                        query = """
                            SELECT strand_name, start_time, args_json, tier, trust_level, tainted
                            FROM active_tasks WHERE task_id = ?
                        """
                        cur.execute(query, (task_id,))
                        row = cur.fetchone()
                        if row:
                            record = TaskRecord(
                                task_id=task_id,
                                strand_name=row[0],
                                start_time=row[1],
                                args=json.loads(row[2]) if row[2] else {},
                                tier=row[3],
                                trust_level=row[4],
                                tainted=bool(row[5]),
                            )
                except (sqlite3.Error, OSError) as e:
                    logger.debug("CoreTapestry DB query error: %s", e)

            if record:
                record.success = success
                record.duration_ms = duration_ms
                record.error = error
                self._task_history.append(record)
                if self._persist:
                    try:
                        with _get_connection() as conn:
                            conn.execute("DELETE FROM active_tasks WHERE task_id = ?", (task_id,))
                            query = """
                                INSERT INTO task_history
                                (task_id, strand_name, start_time, duration_ms, success, error,
                                 tier, trust_level, tainted, args_json)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """
                            conn.execute(
                                query,
                                (
                                    record.task_id,
                                    record.strand_name,
                                    record.start_time,
                                    record.duration_ms,
                                    1 if record.success else 0,
                                    record.error,
                                    record.tier,
                                    record.trust_level,
                                    1 if record.tainted else 0,
                                    json.dumps(record.args),
                                ),
                            )
                    except (sqlite3.Error, OSError) as e:
                        logger.debug("CoreTapestry DB error on end: %s", e)
        return record

    def cancel_task(self, identifier: str) -> str:
        clean_id = identifier.strip()
        if not clean_id:
            return "Error: No task identifier or strand name specified to cancel."

        with self._lock:
            for tid, task in list(self._active_tasks.items()):
                if clean_id in (tid, task.strand_name):
                    self._active_tasks.pop(tid, None)
                    if self._persist:
                        try:
                            with _get_connection() as conn:
                                conn.execute("DELETE FROM active_tasks WHERE task_id = ?", (tid,))
                        except (sqlite3.Error, OSError) as e:
                            logger.debug("CoreTapestry DB cancel error: %s", e)
                    return f"Successfully cancelled active task '{task.strand_name}' (ID: {tid})."

            if self._persist:
                try:
                    with _get_connection() as conn:
                        cur = conn.cursor()
                        query = """
                            SELECT task_id, strand_name FROM active_tasks
                            WHERE task_id = ? OR strand_name = ?
                        """
                        cur.execute(query, (clean_id, clean_id))
                        row = cur.fetchone()
                        if row:
                            tid, sname = row[0], row[1]
                            conn.execute("DELETE FROM active_tasks WHERE task_id = ?", (tid,))
                            return f"Successfully cancelled active task '{sname}' (ID: {tid})."
                except (sqlite3.Error, OSError) as e:
                    logger.debug("CoreTapestry DB search cancel error: %s", e)

        return f"No active task matching '{clean_id}' currently running."

    def get_active_tasks(self) -> list[dict[str, Any]]:
        with self._lock:
            if not self._persist:
                return [t.model_dump() for t in self._active_tasks.values()]
            try:
                with _get_connection() as conn:
                    cur = conn.cursor()
                    query = """
                        SELECT task_id, strand_name, start_time, args_json, tier, trust_level, tainted
                        FROM active_tasks
                    """
                    cur.execute(query)
                    tasks = []
                    for row in cur.fetchall():
                        tasks.append(
                            TaskRecord(
                                task_id=row[0],
                                strand_name=row[1],
                                start_time=row[2],
                                args=json.loads(row[3]) if row[3] else {},
                                tier=row[4],
                                trust_level=row[5],
                                tainted=bool(row[6]),
                            ).model_dump()
                        )
                    return tasks
            except (sqlite3.Error, OSError) as e:
                logger.debug("CoreTapestry get_active_tasks DB error: %s", e)
                return [t.model_dump() for t in self._active_tasks.values()]

    def get_task_history(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            if not self._persist:
                items = list(self._task_history)
                return [t.model_dump() for t in items[-limit:]]
            try:
                with _get_connection() as conn:
                    cur = conn.cursor()
                    query = """
                        SELECT task_id, strand_name, start_time, duration_ms, success, error,
                               tier, trust_level, tainted, args_json
                        FROM task_history ORDER BY id DESC LIMIT ?
                    """
                    cur.execute(query, (limit,))
                    rows = cur.fetchall()
                    history = []
                    for row in reversed(rows):
                        history.append(
                            TaskRecord(
                                task_id=row[0],
                                strand_name=row[1],
                                start_time=row[2],
                                duration_ms=row[3],
                                success=bool(row[4]),
                                error=row[5],
                                tier=row[6],
                                trust_level=row[7],
                                tainted=bool(row[8]),
                                args=json.loads(row[9]) if row[9] else {},
                            ).model_dump()
                        )
                    return history
            except (sqlite3.Error, OSError) as e:
                logger.debug("CoreTapestry get_task_history DB error: %s", e)
                items = list(self._task_history)
                return [t.model_dump() for t in items[-limit:]]

    def clear(self) -> None:
        """Clear active tasks and execution history."""
        with self._lock:
            self._active_tasks.clear()
            self._task_history.clear()
            if self._persist:
                try:
                    with _get_connection() as conn:
                        conn.execute("DELETE FROM active_tasks")
                        conn.execute("DELETE FROM task_history")
                except (sqlite3.Error, OSError) as e:
                    logger.debug("CoreTapestry clear DB error: %s", e)

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
    Synchronizes state across processes via SQLite WAL mode.
    """

    def __init__(self, max_notices: int = 100, persist: bool = False):
        self._max_notices = max_notices
        self._persist = persist
        self._lock = threading.RLock()
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
            if self._persist:
                try:
                    with _get_connection() as conn:
                        query = """
                            INSERT INTO notices (timestamp, level, source, message, data_json)
                            VALUES (?, ?, ?, ?, ?)
                        """
                        conn.execute(
                            query,
                            (
                                notice.timestamp,
                                notice.level.value,
                                notice.source,
                                notice.message,
                                json.dumps(notice.data),
                            ),
                        )
                except (sqlite3.Error, OSError) as e:
                    logger.debug("SensoryTapestry stitch DB error: %s", e)

        # Broadcast simultaneously to Warp for real-time streaming listeners
        try:
            warp.publish(f"tapestry.{lvl.value.lower()}", notice.model_dump())
        except (AttributeError, TypeError, ValueError, KeyError, OSError, RuntimeError) as e:
            logger.warning("Failed to broadcast notice to Warp: %s", e)

        return notice

    def set_slot(self, key: str, value: Any) -> None:
        """Set a retained state slot in the sensory blackboard."""
        clean_key = str(key).strip()
        with self._lock:
            self._slots[clean_key] = value
            if self._persist:
                try:
                    with _get_connection() as conn:
                        query = """
                            INSERT INTO slots (key, val_json) VALUES (?, ?)
                            ON CONFLICT(key) DO UPDATE SET val_json=excluded.val_json
                        """
                        conn.execute(query, (clean_key, json.dumps(value)))
                except (sqlite3.Error, OSError) as e:
                    logger.debug("SensoryTapestry set_slot DB error: %s", e)

    def get_slot(self, key: str, default: Any = None) -> Any:
        """Get a retained state slot value."""
        clean_key = str(key).strip()
        with self._lock:
            if not self._persist:
                return self._slots.get(clean_key, default)
            try:
                with _get_connection() as conn:
                    cur = conn.cursor()
                    cur.execute("SELECT val_json FROM slots WHERE key = ?", (clean_key,))
                    row = cur.fetchone()
                    if row and row[0] is not None:
                        return json.loads(row[0])
            except (sqlite3.Error, OSError, json.JSONDecodeError) as e:
                logger.debug("SensoryTapestry get_slot DB error: %s", e)
            return self._slots.get(clean_key, default)

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
            if not self._persist:
                items = list(self._notices)
                filtered = []
                for n in items:
                    if target_lvl and n.level != target_lvl:
                        continue
                    if source and n.source.lower() != str(source).lower().strip():
                        continue
                    filtered.append(n.model_dump())
                return filtered[-limit:]

            try:
                with _get_connection() as conn:
                    cur = conn.cursor()
                    query = "SELECT timestamp, level, source, message, data_json FROM notices"
                    params: list[Any] = []
                    conditions = []
                    if target_lvl:
                        conditions.append("level = ?")
                        params.append(target_lvl.value)
                    if source:
                        conditions.append("LOWER(source) = ?")
                        params.append(str(source).lower().strip())
                    if conditions:
                        query += " WHERE " + " AND ".join(conditions)
                    query += " ORDER BY id DESC LIMIT ?"
                    params.append(limit)

                    cur.execute(query, params)
                    rows = cur.fetchall()
                    result = []
                    for row in reversed(rows):
                        result.append(
                            Notice(
                                timestamp=row[0],
                                level=NoticeLevel(row[1]),
                                source=row[2],
                                message=row[3],
                                data=json.loads(row[4]) if row[4] else {},
                            ).model_dump()
                        )
                    return result
            except (sqlite3.Error, OSError, json.JSONDecodeError) as e:
                logger.debug("SensoryTapestry get_notices DB error: %s", e)
                items = list(self._notices)
                return [n.model_dump() for n in items[-limit:]]

    def clear(self) -> None:
        """Clear all sensory state slots and notices."""
        with self._lock:
            self._slots.clear()
            self._notices.clear()
            if self._persist:
                try:
                    with _get_connection() as conn:
                        conn.execute("DELETE FROM slots")
                        conn.execute("DELETE FROM notices")
                except (sqlite3.Error, OSError) as e:
                    logger.debug("SensoryTapestry clear DB error: %s", e)

    def get_state(self) -> dict[str, Any]:
        """Return snapshot of sensory state slots and recent stitched notices."""
        with self._lock:
            if not self._persist:
                return {
                    "slots": dict(self._slots),
                    "recent_notices": self.get_notices(limit=20),
                }
            try:
                with _get_connection() as conn:
                    cur = conn.cursor()
                    cur.execute("SELECT key, val_json FROM slots")
                    slots_copy = {}
                    for row in cur.fetchall():
                        with contextlib.suppress(json.JSONDecodeError, TypeError):
                            slots_copy[row[0]] = json.loads(row[1]) if row[1] else None
                    return {
                        "slots": slots_copy,
                        "recent_notices": self.get_notices(limit=20),
                    }
            except (sqlite3.Error, OSError) as e:
                logger.debug("SensoryTapestry get_state DB error: %s", e)
                return {
                    "slots": dict(self._slots),
                    "recent_notices": self.get_notices(limit=20),
                }


# Global Shared Singletons (persisted to runtime tmpfs for cross-process IPC)
core_tapestry = CoreTapestry(persist=True)
sensory_tapestry = SensoryTapestry(persist=True)
