"""
Textile Tapestry - Core Task Ledger & Open Sensory Blackboard.
Unified single-engine SQLite storage for high-speed, thread-safe, and process-safe IPC state.
"""

import contextlib
import json
import logging
import os
import sqlite3
import tempfile
import threading
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

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


class TapestryDB:
    """Unified SQLite WAL storage manager for Task Ledger and Sensory Blackboard."""

    def __init__(self, persist: bool = True):
        if persist:
            self._db_path = str(_get_runtime_dir() / "tapestry.db")
            self._uri = False
        else:
            self._db_path = f"file:memdb_{id(self)}?mode=memory&cache=shared"
            self._uri = True
        self._lock = threading.RLock()
        self._local = threading.local()
        self._init_db()

    def get_conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self._db_path, timeout=15.0, uri=self._uri)
            conn.execute("PRAGMA busy_timeout=15000;")
            if not self._uri:
                conn.execute("PRAGMA journal_mode=WAL;")
                conn.execute("PRAGMA synchronous=NORMAL;")
            self._local.conn = conn
        return conn

    def _init_db(self) -> None:
        with self._lock, self.get_conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS active_tasks (
                    task_id TEXT PRIMARY KEY,
                    strand_name TEXT NOT NULL,
                    start_time TEXT NOT NULL,
                    args_json TEXT,
                    tier TEXT,
                    trust_level TEXT,
                    tainted INTEGER DEFAULT 0
                );
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
                CREATE TABLE IF NOT EXISTS slots (
                    key TEXT PRIMARY KEY,
                    val_json TEXT
                );
                CREATE TABLE IF NOT EXISTS notices (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    level TEXT NOT NULL,
                    source TEXT NOT NULL,
                    message TEXT NOT NULL,
                    data_json TEXT
                );
                CREATE TABLE IF NOT EXISTS elastic_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL,
                    topic TEXT NOT NULL,
                    source TEXT NOT NULL,
                    urgency TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    data_json TEXT,
                    timestamp REAL NOT NULL,
                    process_id INTEGER NOT NULL,
                    retained_slot TEXT,
                    retained_value_json TEXT
                );
            """)


class CoreTapestry:
    """Core Task Ledger: Strictly manages engine execution, active tasks, and history via SQLite."""

    def __init__(self, max_history: int = 50, persist: bool = False):
        self._db = TapestryDB(persist=persist)

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
        with self._db._lock, self._db.get_conn() as conn:
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
        return record

    def record_task_end(
        self,
        task_id: str,
        success: bool = True,
        duration_ms: float = 0.0,
        error: str | None = None,
    ) -> TaskRecord | None:
        with self._db._lock, self._db.get_conn() as conn:
            cur = conn.cursor()
            query = """
                SELECT strand_name, start_time, args_json, tier, trust_level, tainted
                FROM active_tasks WHERE task_id = ?
            """
            cur.execute(query, (task_id,))
            row = cur.fetchone()
            if not row:
                return None

            record = TaskRecord(
                task_id=task_id,
                strand_name=row[0],
                start_time=row[1],
                args=json.loads(row[2]) if row[2] else {},
                tier=row[3],
                trust_level=row[4],
                tainted=bool(row[5]),
                success=success,
                duration_ms=duration_ms,
                error=error,
            )

            conn.execute("DELETE FROM active_tasks WHERE task_id = ?", (task_id,))
            insert_query = """
                INSERT INTO task_history
                (task_id, strand_name, start_time, duration_ms, success, error,
                 tier, trust_level, tainted, args_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            conn.execute(
                insert_query,
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
            return record

    def cancel_task(self, identifier: str) -> str:
        clean_id = identifier.strip()
        if not clean_id:
            return "Error: No task identifier or strand name specified to cancel."

        with self._db._lock, self._db.get_conn() as conn:
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

        return f"No active task matching '{clean_id}' currently running."

    def get_active_tasks(self) -> list[dict[str, Any]]:
        with self._db._lock, self._db.get_conn() as conn:
            cur = conn.cursor()
            query = """
                SELECT task_id, strand_name, start_time, args_json, tier, trust_level, tainted
                FROM active_tasks
            """
            cur.execute(query)
            return [
                TaskRecord(
                    task_id=r[0],
                    strand_name=r[1],
                    start_time=r[2],
                    args=json.loads(r[3]) if r[3] else {},
                    tier=r[4],
                    trust_level=r[5],
                    tainted=bool(r[6]),
                ).model_dump()
                for r in cur.fetchall()
            ]

    def get_task_history(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._db._lock, self._db.get_conn() as conn:
            cur = conn.cursor()
            query = """
                SELECT task_id, strand_name, start_time, duration_ms, success, error,
                       tier, trust_level, tainted, args_json
                FROM task_history ORDER BY id DESC LIMIT ?
            """
            cur.execute(query, (limit,))
            return [
                TaskRecord(
                    task_id=r[0],
                    strand_name=r[1],
                    start_time=r[2],
                    duration_ms=r[3],
                    success=bool(r[4]),
                    error=r[5],
                    tier=r[6],
                    trust_level=r[7],
                    tainted=bool(r[8]),
                    args=json.loads(r[9]) if r[9] else {},
                ).model_dump()
                for r in reversed(cur.fetchall())
            ]

    def clear(self) -> None:
        """Clear active tasks and execution history."""
        with self._db._lock, self._db.get_conn() as conn:
            conn.execute("DELETE FROM active_tasks")
            conn.execute("DELETE FROM task_history")

    def get_state(self) -> dict[str, Any]:
        """Return snapshot of running engine tasks and recent execution history."""
        return {
            "active_tasks": self.get_active_tasks(),
            "task_history": self.get_task_history(limit=20),
        }


class SensoryTapestry:
    """Open Sensory Blackboard: Retained state slots and notice feed via SQLite."""

    def __init__(self, max_notices: int = 100, persist: bool = False):
        self._db = TapestryDB(persist=persist)

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
        with self._db._lock, self._db.get_conn() as conn:
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

        return notice

    def set_slot(self, key: str, value: Any) -> None:
        """Set a retained state slot in the sensory blackboard."""
        clean_key = str(key).strip()
        with self._db._lock, self._db.get_conn() as conn:
            query = """
                INSERT INTO slots (key, val_json) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET val_json=excluded.val_json
            """
            conn.execute(query, (clean_key, json.dumps(value)))

    def get_slot(self, key: str, default: Any = None) -> Any:
        """Get a retained state slot value."""
        clean_key = str(key).strip()
        with self._db._lock, self._db.get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT val_json FROM slots WHERE key = ?", (clean_key,))
            row = cur.fetchone()
            if row and row[0] is not None:
                with contextlib.suppress(json.JSONDecodeError):
                    return json.loads(row[0])
        return default

    def get_notices(
        self,
        level: str | NoticeLevel | None = None,
        source: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Retrieve recent notices with optional level and source filtering."""
        target_lvl: str | None = None
        if level:
            if isinstance(level, str):
                try:
                    target_lvl = NoticeLevel(level.upper().strip()).value
                except ValueError:
                    target_lvl = None
            else:
                target_lvl = level.value

        with self._db._lock, self._db.get_conn() as conn:
            cur = conn.cursor()
            query = "SELECT timestamp, level, source, message, data_json FROM notices"
            params: list[Any] = []
            conditions = []
            if target_lvl:
                conditions.append("level = ?")
                params.append(target_lvl)
            if source:
                conditions.append("LOWER(source) = ?")
                params.append(str(source).lower().strip())
            if conditions:
                query += " WHERE " + " AND ".join(conditions)
            query += " ORDER BY id DESC LIMIT ?"
            params.append(limit)

            cur.execute(query, params)
            return [
                Notice(
                    timestamp=r[0],
                    level=NoticeLevel(r[1]),
                    source=r[2],
                    message=r[3],
                    data=json.loads(r[4]) if r[4] else {},
                ).model_dump()
                for r in reversed(cur.fetchall())
            ]

    def record_elastic_event(
        self,
        event_id: str,
        topic: str,
        source: str,
        urgency: str,
        summary: str,
        data: dict[str, Any],
        timestamp: float,
        process_id: int,
        retained_slot: str | None = None,
        retained_value: Any = None,
    ) -> int:
        """Record an Elastic event into the shared SQLite event stream for cross-process IPC."""
        with self._db._lock, self._db.get_conn() as conn:
            query = """
                INSERT INTO elastic_events (
                    event_id, topic, source, urgency, summary, data_json,
                    timestamp, process_id, retained_slot, retained_value_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            cur = conn.execute(
                query,
                (
                    str(event_id),
                    str(topic),
                    str(source),
                    str(urgency),
                    str(summary),
                    json.dumps(data) if data else "{}",
                    float(timestamp),
                    int(process_id),
                    retained_slot,
                    json.dumps(retained_value) if retained_value is not None else None,
                ),
            )
            inserted_id = cur.lastrowid or 0

            # Prune old events if table grows over 1000 items
            if inserted_id % 50 == 0:
                conn.execute(
                    "DELETE FROM elastic_events WHERE id < (SELECT max(id) - 500 FROM elastic_events)"
                )

            return inserted_id

    def get_max_elastic_event_id(self) -> int:
        """Get the latest event ID currently in the database."""
        with self._db._lock, self._db.get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT COALESCE(MAX(id), 0) FROM elastic_events")
            row = cur.fetchone()
            return int(row[0]) if row else 0

    def get_elastic_events_since(self, last_id: int, limit: int = 100) -> list[dict[str, Any]]:
        """Query all Elastic events inserted after last_id for cross-process event polling."""
        with self._db._lock, self._db.get_conn() as conn:
            cur = conn.cursor()
            query = """
                SELECT id, event_id, topic, source, urgency, summary, data_json,
                       timestamp, process_id, retained_slot, retained_value_json
                FROM elastic_events
                WHERE id > ?
                ORDER BY id ASC
                LIMIT ?
            """
            cur.execute(query, (int(last_id), int(limit)))
            events = []
            for r in cur.fetchall():
                try:
                    payload_data = json.loads(r[6]) if r[6] else {}
                except (json.JSONDecodeError, TypeError):
                    payload_data = {}

                try:
                    retained_val = json.loads(r[10]) if r[10] else None
                except (json.JSONDecodeError, TypeError):
                    retained_val = None

                events.append({
                    "seq_id": r[0],
                    "id": r[1],
                    "topic": r[2],
                    "source": r[3],
                    "urgency": r[4],
                    "summary": r[5],
                    "data": payload_data,
                    "timestamp": r[7],
                    "process_id": r[8],
                    "retained_slot": r[9],
                    "retained_value": retained_val,
                })
            return events

    def clear(self) -> None:
        """Clear all sensory state slots and notices."""
        with self._db._lock, self._db.get_conn() as conn:
            conn.execute("DELETE FROM slots")
            conn.execute("DELETE FROM notices")
            conn.execute("DELETE FROM elastic_events")

    def get_state(self) -> dict[str, Any]:
        """Return snapshot of sensory state slots and recent stitched notices."""
        with self._db._lock, self._db.get_conn() as conn:
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


# Global Shared Singletons (persisted to runtime tmpfs for cross-process IPC)
core_tapestry = CoreTapestry(persist=True)
sensory_tapestry = SensoryTapestry(persist=True)
