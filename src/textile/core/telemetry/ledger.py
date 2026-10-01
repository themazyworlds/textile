"""
Textile Task Ledger Engine.
Provides task execution tracking, active task management, and execution history.
"""

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from textile.core.telemetry.database import TapestryDatabase

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class TaskOptions:
    args: dict[str, Any] | None = None
    tier: str | None = None


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


class CoreTapestry:
    """Core Task Ledger: Strictly manages engine execution, active tasks, and history via SQLite."""

    def __init__(self, persist: bool = False):
        self._database = TapestryDatabase(persist=persist)

    def record_task_start(
        self,
        task_id: str,
        strand_name: str,
        options: TaskOptions | dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> TaskRecord:
        if isinstance(options, dict):
            opts = TaskOptions(args=options, **kwargs)
        elif isinstance(options, TaskOptions):
            opts = options
        else:
            opts = TaskOptions(**kwargs)
        record = TaskRecord(
            task_id=task_id,
            strand_name=strand_name,
            start_time=datetime.now(UTC).isoformat(),
            args=opts.args or {},
            tier=opts.tier,
        )
        with self._database._lock, self._database.get_connection() as connection:
            query = """
                INSERT OR REPLACE INTO active_tasks
                (task_id, strand_name, start_time, args_json, tier)
                VALUES (?, ?, ?, ?, ?)
            """
            connection.execute(
                query,
                (
                    record.task_id,
                    record.strand_name,
                    record.start_time,
                    json.dumps(record.args),
                    record.tier,
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
        with self._database._lock, self._database.get_connection() as connection:
            cursor = connection.cursor()
            query = """
                SELECT strand_name, start_time, args_json, tier
                FROM active_tasks WHERE task_id = ?
            """
            cursor.execute(query, (task_id,))
            row = cursor.fetchone()
            if not row:
                return None

            record = TaskRecord(
                task_id=task_id,
                strand_name=row[0],
                start_time=row[1],
                args=json.loads(row[2]) if row[2] else {},
                tier=row[3],
                success=success,
                duration_ms=duration_ms,
                error=error,
            )

            connection.execute("DELETE FROM active_tasks WHERE task_id = ?", (task_id,))
            insert_query = """
                INSERT INTO task_history
                (task_id, strand_name, start_time, duration_ms, success, error, tier, args_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """
            connection.execute(
                insert_query,
                (
                    record.task_id,
                    record.strand_name,
                    record.start_time,
                    record.duration_ms,
                    1 if record.success else 0,
                    record.error,
                    record.tier,
                    json.dumps(record.args),
                ),
            )
            return record

    def cancel_task(self, identifier: str) -> str:
        clean_id = identifier.strip()
        if not clean_id:
            return "Error: No task identifier or strand name specified to cancel."

        with self._database._lock, self._database.get_connection() as connection:
            cursor = connection.cursor()
            query = """
                SELECT task_id, strand_name FROM active_tasks
                WHERE task_id = ? OR strand_name = ?
            """
            cursor.execute(query, (clean_id, clean_id))
            if row := cursor.fetchone():
                tid, sname = row[0], row[1]
                connection.execute("DELETE FROM active_tasks WHERE task_id = ?", (tid,))
                return f"Successfully cancelled active task '{sname}' (ID: {tid})."

        return f"No active task matching '{clean_id}' currently running."

    def get_active_tasks(self) -> list[dict[str, Any]]:
        with self._database._lock, self._database.get_connection() as connection:
            cursor = connection.cursor()
            query = """
                SELECT task_id, strand_name, start_time, args_json, tier
                FROM active_tasks
            """
            cursor.execute(query)
            return [
                TaskRecord(
                    task_id=r[0],
                    strand_name=r[1],
                    start_time=r[2],
                    args=json.loads(r[3]) if r[3] else {},
                    tier=r[4],
                ).model_dump()
                for r in cursor.fetchall()
            ]

    def get_task_history(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._database._lock, self._database.get_connection() as connection:
            cursor = connection.cursor()
            query = """
                SELECT task_id, strand_name, start_time, duration_ms, success, error, tier, args_json
                FROM task_history ORDER BY id DESC LIMIT ?
            """
            cursor.execute(query, (limit,))
            return [
                TaskRecord(
                    task_id=r[0],
                    strand_name=r[1],
                    start_time=r[2],
                    duration_ms=r[3],
                    success=bool(r[4]),
                    error=r[5],
                    tier=r[6],
                    args=json.loads(r[7]) if r[7] else {},
                ).model_dump()
                for r in reversed(cursor.fetchall())
            ]

    def clear(self) -> None:
        """Clear active tasks and execution history."""
        with self._database._lock, self._database.get_connection() as connection:
            connection.execute("DELETE FROM active_tasks")
            connection.execute("DELETE FROM task_history")

    def get_state(self) -> dict[str, Any]:
        """Return snapshot of running engine tasks and recent execution history."""
        return {
            "active_tasks": self.get_active_tasks(),
            "task_history": self.get_task_history(limit=20),
        }


core_tapestry = CoreTapestry(persist=True)
