"""
Textile Open Sensory Blackboard Engine.
Provides state slot retention, notice feeds, and Elastic cross-process IPC events.
"""

import contextlib
import json
import logging
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from textile.core.telemetry.database import TapestryDatabase

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ElasticEventSpec:
    event_id: str
    topic: str
    source: str
    urgency: str
    summary: str
    data: dict[str, Any] | None = None
    timestamp: float | None = None
    process_id: int | None = None
    retained_slot: str | None = None
    retained_value: Any = None


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


class SensoryTapestry:
    """Open Sensory Blackboard: Retained state slots and notice feed via SQLite."""

    def __init__(self, max_notices: int = 100, persist: bool = False):
        self._max_notices = max_notices
        self._database = TapestryDatabase(persist=persist)
        self._slots_lock = threading.RLock()
        self._slots_cache: dict[str, Any] = {}
        self._load_cached_slots()

    def _load_cached_slots(self) -> None:
        with self._slots_lock, self._database._lock, self._database.get_connection() as connection:
            cursor = connection.cursor()
            cursor.execute("SELECT key, val_json FROM slots")
            for row in cursor.fetchall():
                with contextlib.suppress(json.JSONDecodeError, TypeError):
                    self._slots_cache[row[0]] = json.loads(row[1]) if row[1] else None

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
            source=source.strip(),
            message=message.strip(),
            data=data or {},
        )
        with self._database._lock, self._database.get_connection() as connection:
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
                    json.dumps(notice.data),
                ),
            )

        return notice

    def set_slot(self, key: str, value: Any) -> None:
        """Set a retained state slot in the sensory blackboard."""
        clean_key = key.strip()
        with self._slots_lock:
            self._slots_cache[clean_key] = value
        with self._database._lock, self._database.get_connection() as connection:
            query = """
                INSERT INTO slots (key, val_json) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET val_json=excluded.val_json
            """
            connection.execute(query, (clean_key, json.dumps(value)))

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

        with self._database._lock, self._database.get_connection() as connection:
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
                Notice(
                    timestamp=r[0],
                    level=NoticeLevel(r[1]),
                    source=r[2],
                    message=r[3],
                    data=json.loads(r[4]) if r[4] else {},
                ).model_dump()
                for r in reversed(cursor.fetchall())
            ]

    def record_elastic_event(
        self,
        spec: ElasticEventSpec | None = None,
        **kwargs: Any,
    ) -> int:
        """Record an Elastic event into the shared SQLite event stream for cross-process IPC."""
        s = spec or ElasticEventSpec(**kwargs)
        with self._database._lock, self._database.get_connection() as connection:
            query = """
                INSERT INTO elastic_events (
                    event_id, topic, source, urgency, summary, data_json,
                    timestamp, process_id, retained_slot, retained_value_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            cursor = connection.execute(
                query,
                (
                    s.event_id,
                    s.topic,
                    s.source,
                    s.urgency,
                    s.summary,
                    json.dumps(s.data) if s.data else "{}",
                    float(s.timestamp or 0.0),
                    int(s.process_id or 0),
                    s.retained_slot,
                    json.dumps(s.retained_value) if s.retained_value is not None else None,
                ),
            )
            inserted_id = cursor.lastrowid or 0

            # Prune old events if table grows over 1000 items
            if inserted_id % 50 == 0:
                connection.execute("DELETE FROM elastic_events WHERE id < (SELECT max(id) - 500 FROM elastic_events)")

            return inserted_id

    def get_max_elastic_event_id(self) -> int:
        """Get the latest event ID currently in the database."""
        with self._database._lock, self._database.get_connection() as connection:
            cursor = connection.cursor()
            cursor.execute("SELECT COALESCE(MAX(id), 0) FROM elastic_events")
            row = cursor.fetchone()
            return int(row[0]) if row else 0

    def get_elastic_events_since(self, last_id: int, limit: int = 100) -> list[dict[str, Any]]:
        """Query all Elastic events inserted after last_id for cross-process event polling."""
        with self._database._lock, self._database.get_connection() as connection:
            cursor = connection.cursor()
            query = """
                SELECT id, event_id, topic, source, urgency, summary, data_json,
                       timestamp, process_id, retained_slot, retained_value_json
                FROM elastic_events
                WHERE id > ?
                ORDER BY id ASC
                LIMIT ?
            """
            cursor.execute(query, (last_id, limit))
            events = []
            for r in cursor.fetchall():
                try:
                    payload_data = json.loads(r[6]) if r[6] else {}
                except (json.JSONDecodeError, TypeError):
                    payload_data = {}

                try:
                    retained_val = json.loads(r[10]) if r[10] else None
                except (json.JSONDecodeError, TypeError):
                    retained_val = None

                events.append(
                    {
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
                    }
                )
            return events

    def clear(self) -> None:
        """Clear all sensory state slots and notices."""
        with self._slots_lock:
            self._slots_cache.clear()
        with self._database._lock, self._database.get_connection() as connection:
            connection.execute("DELETE FROM slots")
            connection.execute("DELETE FROM notices")
            connection.execute("DELETE FROM elastic_events")

    def get_state(self) -> dict[str, Any]:
        """Return snapshot of sensory state slots and recent stitched notices."""
        with self._slots_lock:
            slots_copy = dict(self._slots_cache)
        return {
            "slots": slots_copy,
            "recent_notices": self.get_notices(limit=20),
        }


sensory_tapestry = SensoryTapestry(persist=True)
