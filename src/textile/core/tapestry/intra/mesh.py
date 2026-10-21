"""
Textile Task Ledger Engine.
Provides task execution tracking, active task management, and execution history.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import orjson

from textile.core.tapestry.database import TapestryDatabase, get_default_database
lazy from textile.core.camshaft import camshaft


@dataclass(slots=True)
class TaskOptions:
    args: dict[str, Any] | None = None
    tier: str | None = None


@dataclass(slots=True)
class TaskRecord:
    """Engine task execution tracking."""

    task_id: str
    strand_name: str
    start_time: str
    args: dict[str, Any] = field(default_factory=dict)
    duration_ms: float | None = None
    success: bool | None = None
    error: str | None = None
    tier: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "strand_name": self.strand_name,
            "start_time": self.start_time,
            "args": self.args,
            "duration_ms": self.duration_ms,
            "success": self.success,
            "error": self.error,
            "tier": self.tier,
        }

    def model_dump(self) -> dict[str, Any]:
        return self.to_dict()


class CoreTapestry:
    """Core Task Ledger: Strictly manages engine execution, active tasks, and history via SQLite."""

    def __init__(
        self,
        persist: bool = False,
        database: TapestryDatabase | None = None,
    ):
        self._database = database or get_default_database(persist=persist)

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
        with self._database.transaction() as connection:
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
                    orjson.dumps(record.args).decode(),
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
        with self._database.transaction() as connection:
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
                args=orjson.loads(row[2]) if row[2] else {},
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
                    orjson.dumps(record.args).decode(),
                ),
            )
            return record

    def cancel_task(self, identifier: str) -> str:
        clean_id = identifier.strip()
        if not clean_id:
            return "Error: No task identifier or strand name specified to cancel."

        with self._database.transaction() as connection:
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
        with self._database.transaction() as connection:
            cursor = connection.cursor()
            query = """
                SELECT task_id, strand_name, start_time, args_json, tier
                FROM active_tasks
            """
            cursor.execute(query)
            return [
                {
                    "task_id": r[0],
                    "strand_name": r[1],
                    "start_time": r[2],
                    "args": orjson.loads(r[3]) if r[3] else {},
                    "tier": r[4],
                }
                for r in cursor.fetchall()
            ]

    def get_task_history(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._database.transaction() as connection:
            cursor = connection.cursor()
            query = """
                SELECT task_id, strand_name, start_time, duration_ms, success, error, tier, args_json
                FROM task_history ORDER BY id DESC LIMIT ?
            """
            cursor.execute(query, (limit,))
            return [
                {
                    "task_id": r[0],
                    "strand_name": r[1],
                    "start_time": r[2],
                    "duration_ms": r[3],
                    "success": bool(r[4]),
                    "error": r[5],
                    "tier": r[6],
                    "args": orjson.loads(r[7]) if r[7] else {},
                }
                for r in reversed(cursor.fetchall())
            ]

    def clear(self) -> None:
        """Clear active tasks and execution history."""
        with self._database.transaction() as connection:
            connection.execute("DELETE FROM active_tasks")
            connection.execute("DELETE FROM task_history")

    def get_state(self) -> dict[str, Any]:
        """Return snapshot of running engine tasks and recent execution history."""
        return {
            "active_tasks": self.get_active_tasks(),
            "task_history": self.get_task_history(limit=20),
        }

    get_engine_state = get_state


core_tapestry = CoreTapestry(persist=True)
intra_mesh = core_tapestry
IntraMesh = CoreTapestry

__all__ = ["CoreTapestry", "IntraMesh", "TaskOptions", "TaskRecord", "core_tapestry", "intra_mesh"]


@camshaft.on("strand_execution_started")
def _on_strand_started(_sender: Any = None, **kwargs: Any) -> None:
    core_tapestry.record_task_start(
        kwargs.get("task_id", ""),
        kwargs.get("strand_name", ""),
        args=kwargs.get("args", {}),
        tier=kwargs.get("tier_val", ""),
    )


@camshaft.on("strand_executed")
def _on_strand_completed(_sender: Any = None, **kwargs: Any) -> None:
    core_tapestry.record_task_end(
        kwargs.get("task_id", ""),
        success=kwargs.get("success", False),
        duration_ms=kwargs.get("duration_ms", 0.0),
        error=kwargs.get("error"),
    )
