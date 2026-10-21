"""
Textile Open Sensory Blackboard Engine.
Provides state slot retention, notice feeds, and Elastic cross-process IPC events.
"""

import contextlib
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

import orjson

from textile.core.tapestry.database import TapestryDatabase, get_default_database
lazy from textile.core.camshaft import camshaft


class NoticeLevel(StrEnum):
    """Notice and Alert priority levels for the Sensory Tapestry Blackboard."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    NOTICE = "NOTICE"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


@dataclass(slots=True)
class Notice:
    """A structured sensory/system notice stitched into Sensory Tapestry."""

    source: str
    message: str
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    level: NoticeLevel = NoticeLevel.INFO
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "level": self.level,
            "source": self.source,
            "message": self.message,
            "data": self.data,
        }

    def model_dump(self) -> dict[str, Any]:
        return self.to_dict()


class SensoryTapestry:
    """Open Sensory Blackboard: Retained state slots and notice feed via SQLite."""

    def __init__(
        self,
        max_notices: int = 100,
        persist: bool = False,
        database: TapestryDatabase | None = None,
    ):
        self._max_notices = max_notices
        self._database = database or get_default_database(persist=persist)
        self._slots_lock = threading.RLock()
        self._slots_cache: dict[str, Any] = {}
        self._load_cached_slots()

    def _load_cached_slots(self) -> None:
        with self._slots_lock, self._database.transaction() as connection:
            cursor = connection.cursor()
            cursor.execute("SELECT key, val_json FROM slots")
            for row in cursor.fetchall():
                with contextlib.suppress(orjson.JSONDecodeError, TypeError):
                    self._slots_cache[row[0]] = orjson.loads(row[1]) if row[1] else None

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
            source=source.strip(),
            message=message.strip(),
            level=lvl,
            data=data or {},
        )
        with self._database.transaction() as connection:
            query = """
                INSERT INTO notices (timestamp, level, source, message, data_json)
                VALUES (?, ?, ?, ?, ?)
            """
            connection.execute(
                query,
                (
                    notice.timestamp,
                    notice.level.value,
                    notice.source,
                    notice.message,
                    orjson.dumps(notice.data).decode(),
                ),
            )

        return notice

    def set_slot(self, key: str, value: Any) -> None:
        """Set a retained state slot in the sensory blackboard."""
        clean_key = key.strip()
        with self._slots_lock:
            self._slots_cache[clean_key] = value
        with self._database.transaction() as connection:
            query = """
                INSERT INTO slots (key, val_json) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET val_json=excluded.val_json
            """
            connection.execute(query, (clean_key, orjson.dumps(value).decode()))
        camshaft.emit("blackboard_slot_updated", key=clean_key, value=value)

    def get_slot(self, key: str, default: Any = None) -> Any:
        """Get a retained state slot value with sub-microsecond in-memory lookup."""
        clean_key = key.strip()
        with self._slots_lock:
            return self._slots_cache.get(clean_key, default)

    def get_notices(
        self,
        level: str | NoticeLevel | None = None,
        source: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Retrieve recent notices with optional level and source filtering."""
        target_level: str | None = None
        if level:
            if isinstance(level, str):
                try:
                    target_level = NoticeLevel(level.upper().strip()).value
                except ValueError:
                    target_level = None
            else:
                target_level = level.value

        with self._database.transaction() as connection:
            cursor = connection.cursor()
            query = "SELECT timestamp, level, source, message, data_json FROM notices"
            parameters: list[Any] = []
            conditions = []
            if target_level:
                conditions.append("level = ?")
                parameters.append(target_level)
            if source:
                conditions.append("LOWER(source) = ?")
                parameters.append(str(source).lower().strip())
            if conditions:
                query += " WHERE " + " AND ".join(conditions)
            query += " ORDER BY id DESC LIMIT ?"
            parameters.append(limit)

            cursor.execute(query, parameters)
            return [
                {
                    "timestamp": r[0],
                    "level": r[1],
                    "source": r[2],
                    "message": r[3],
                    "data": orjson.loads(r[4]) if r[4] else {},
                }
                for r in reversed(cursor.fetchall())
            ]

    def clear(self) -> None:
        """Clear all sensory state slots and notices."""
        with self._slots_lock:
            self._slots_cache.clear()
        with self._database.transaction() as connection:
            connection.execute("DELETE FROM slots")
            connection.execute("DELETE FROM notices")

    def get_state(self) -> dict[str, Any]:
        """Return snapshot of sensory state slots and recent stitched notices."""
        with self._slots_lock:
            slots_copy = dict(self._slots_cache)
        return {
            "slots": slots_copy,
            "recent_notices": self.get_notices(limit=20),
        }


sensory_tapestry = SensoryTapestry(persist=True)
sensory_mesh = sensory_tapestry
SensoryMesh = SensoryTapestry

__all__ = ["Notice", "NoticeLevel", "SensoryMesh", "SensoryTapestry", "sensory_mesh", "sensory_tapestry"]


@camshaft.on("blackboard_slot_input")
def _on_blackboard_slot_input(_sender: Any = None, *, key: str, value: Any, **_kw: Any) -> None:
    sensory_tapestry.set_slot(key, value)


@camshaft.on("stitch_notice")
def _on_stitch_notice(
    _sender: Any = None,
    *,
    level: str,
    source: str,
    message: str,
    data: dict[str, Any] | None = None,
    **_kw: Any,
) -> Notice:
    return sensory_tapestry.stitch(level=level, source=source, message=message, data=data)


@camshaft.on("strand_executed")
def _on_strand_completed_notice(_sender: Any = None, **kwargs: Any) -> None:
    strand_name = kwargs.get("strand_name", "")
    tier_val = kwargs.get("tier_val", "")
    dur_ms = kwargs.get("duration_ms", 0.0)
    success = kwargs.get("success", False)
    err = kwargs.get("error")
    args = kwargs.get("args", {})
    caller = kwargs.get("caller", "")
    msg = (
        f"Executed '{strand_name}' [{tier_val.upper()}] ({dur_ms:.1f}ms)"
        if success
        else f"Failed '{strand_name}': {err}"
    )
    sensory_tapestry.stitch(
        level=NoticeLevel.INFO if success else NoticeLevel.ERROR,
        source=strand_name,
        message=msg,
        data={"args": args, "caller": caller, "tier": tier_val},
    )
