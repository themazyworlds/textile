"""
Textile Elastic - Unified Event Broadcast & Sensory Subscription Fabric.
Serves as the single front door for both broadcasting and subscribing to system events,
sensory deltas, LLM weft triggers, and Tapestry state updates.
"""

import asyncio
import contextlib
import fnmatch
import inspect
import os
import sqlite3
import threading
import time
import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from textile.core.telemetry.blackboard import NoticeLevel, sensory_tapestry
from textile.core.telemetry.log import get_logger

logger = get_logger(__name__)


class EventUrgency(StrEnum):
    """Urgency / Priority tiers for Elastic events."""

    AMBIENT = "ambient"  # Background telemetry, periodic status (urgency ~0.1)
    NOTICE = "notice"  # Standard state changes, task completion, info (urgency ~0.3)
    ALERT = "alert"  # High priority alerts, warnings, tension sparks (urgency ~0.7)
    FLASH = "flash"  # Critical errors, crashes, immediate emergency (urgency 1.0)

    @property
    def numeric(self) -> float:
        mapping = {
            EventUrgency.AMBIENT: 0.1,
            EventUrgency.NOTICE: 0.3,
            EventUrgency.ALERT: 0.7,
            EventUrgency.FLASH: 1.0,
        }
        return mapping.get(self, 0.3)

    @classmethod
    def from_value(cls, val: Any) -> EventUrgency:
        if isinstance(val, EventUrgency):
            return val
        s = str(val or "").lower().strip()
        if s in {"flash", "crit", "critical", "emerg", "emergency", "1.0", "1"}:
            return EventUrgency.FLASH
        if s in {"alert", "warning", "warn", "0.7", "0.8", "0.9"}:
            return EventUrgency.ALERT
        if s in {"ambient", "debug", "trace", "0.1", "0.2"}:
            return EventUrgency.AMBIENT
        return EventUrgency.NOTICE


@dataclass(slots=True)
class BroadcastOptions:
    source: str = "system"
    urgency: EventUrgency | str = EventUrgency.NOTICE
    data: dict[str, Any] | None = None
    retained_slot: str | None = None
    retained_value: Any = None


class EventFrame(BaseModel):
    """Standardized, self-describing immutable event packet."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:12])
    topic: str
    source: str = "system"
    urgency: EventUrgency = EventUrgency.NOTICE
    summary: str
    data: dict[str, Any] = Field(default_factory=dict)
    timestamp: float = Field(default_factory=time.time)
    process_id: int = Field(default_factory=os.getpid)
    retained_slot: str | None = None
    retained_value: Any = None


class _Subscription:
    def __init__(
        self,
        token: str,
        pattern: str,
        callback: Callable[[EventFrame], Any],
        min_urgency: EventUrgency | None = None,
    ):
        self.token = token
        self.pattern = pattern
        self.callback = callback
        self.min_urgency = min_urgency

    def matches(self, frame: EventFrame) -> bool:
        if self.min_urgency is not None and frame.urgency.numeric < self.min_urgency.numeric:
            return False

        if self.pattern in ("*", frame.topic):
            return True

        return fnmatch.fnmatch(frame.topic, self.pattern)


class ElasticEngine:
    """
    Unified Cross-Process Event Hub & Sensory Routing Fabric.
    Single front door for both broadcasting and subscribing across processes.
    """

    def __init__(self, enable_ipc_poller: bool = True):
        self._lock = threading.RLock()
        self._pid = os.getpid()
        self._subscriptions: dict[str, _Subscription] = {}
        self._async_queues: list[asyncio.Queue[EventFrame]] = []
        self._running = True
        self._ipc_thread: threading.Thread | None = None
        self._last_event_id: int = 0

        if enable_ipc_poller:
            try:
                self._last_event_id = sensory_tapestry.get_max_elastic_event_id()
                self._ipc_thread = threading.Thread(
                    target=self._ipc_worker,
                    daemon=True,
                    name=f"elastic-ipc-{self._pid}",
                )
                self._ipc_thread.start()
            except (sqlite3.Error, OSError, RuntimeError) as e:
                logger.debug("elastic.ipc_worker_start_failed", error=str(e))

    def _ipc_worker(self) -> None:
        """Background thread polling SQLite event log for events from other processes."""
        while self._running:
            try:
                events = sensory_tapestry.get_elastic_events_since(self._last_event_id)
                for ev in events:
                    self._last_event_id = max(self._last_event_id, ev["seq_id"])
                    # Ignore events produced by this exact process (already delivered locally)
                    if ev["process_id"] == self._pid:
                        continue

                    frame = EventFrame(
                        id=ev["id"],
                        topic=ev["topic"],
                        source=ev["source"],
                        urgency=EventUrgency.from_value(ev["urgency"]),
                        summary=ev["summary"],
                        data=ev["data"],
                        timestamp=ev["timestamp"],
                        process_id=ev["process_id"],
                        retained_slot=ev["retained_slot"],
                        retained_value=ev["retained_value"],
                    )
                    self._deliver_local(frame)
            except (sqlite3.Error, OSError, ValueError, KeyError, TypeError, RuntimeError) as e:
                logger.debug("elastic.ipc_poll_notice", error=str(e))

            time.sleep(0.05)

    def broadcast(
        self,
        topic: str,
        summary: str,
        options: BroadcastOptions | str | None = None,
        **kwargs: Any,
    ) -> EventFrame:
        """
        Broadcast an event to all subscribers, persist to Tapestry, and update retained slots.

        :param topic: Hierarchical event topic (e.g., 'timer.expired', 'system.alert', 'sensors.cpu').
        :param summary: Human-readable narrative description of the event.
        :param options: Optional BroadcastOptions instance or source string.
        """
        if isinstance(options, str):
            opts = BroadcastOptions(source=options, **kwargs)
        elif isinstance(options, BroadcastOptions):
            opts = options
        else:
            opts = BroadcastOptions(**kwargs)
        clean_topic = topic.strip()
        clean_source = opts.source.strip()
        parsed_urgency = EventUrgency.from_value(opts.urgency)
        payload_data = dict(opts.data or {})

        frame = EventFrame(
            topic=clean_topic,
            source=clean_source,
            urgency=parsed_urgency,
            summary=summary.strip(),
            data=payload_data,
            timestamp=time.time(),
            process_id=self._pid,
            retained_slot=opts.retained_slot,
            retained_value=opts.retained_value,
        )

        # 1. Update Tapestry Retained Blackboard Slot if specified
        if opts.retained_slot is not None:
            sensory_tapestry.set_slot(opts.retained_slot, opts.retained_value)

        # 2. Deliver in-process immediately (zero latency for local UI & listeners)
        self._deliver_local(frame)

        # 3. Persist Notice & Record to shared SQLite cross-process event stream off-thread
        def _persist_to_sqlite() -> None:
            notice_level = NoticeLevel.INFO
            if parsed_urgency == EventUrgency.FLASH:
                notice_level = NoticeLevel.CRITICAL
            elif parsed_urgency == EventUrgency.ALERT:
                notice_level = NoticeLevel.WARNING
            elif parsed_urgency == EventUrgency.NOTICE:
                notice_level = NoticeLevel.NOTICE

            with contextlib.suppress(sqlite3.Error, OSError, RuntimeError, ValueError):
                sensory_tapestry.stitch(
                    level=notice_level,
                    source=clean_source,
                    message=frame.summary,
                    data={"topic": clean_topic, "urgency": parsed_urgency.value} | payload_data,
                )
                sensory_tapestry.record_elastic_event(
                    event_id=frame.id,
                    topic=frame.topic,
                    source=frame.source,
                    urgency=frame.urgency.value,
                    summary=frame.summary,
                    data=frame.data,
                    timestamp=frame.timestamp,
                    process_id=self._pid,
                    retained_slot=opts.retained_slot,
                    retained_value=opts.retained_value,
                )

        try:
            loop = asyncio.get_running_loop()
            loop.run_in_executor(None, _persist_to_sqlite)
        except RuntimeError:
            _persist_to_sqlite()

        return frame

    def _deliver_local(self, frame: EventFrame) -> None:
        """Deliver EventFrame to local in-process subscribers and async queues."""
        with self._lock:
            subs = list(self._subscriptions.values())
            queues = self._async_queues.copy()

        for sub in subs:
            if sub.matches(frame):
                self._invoke_callback(sub.callback, frame)

        for q in queues:
            with contextlib.suppress(asyncio.QueueFull, RuntimeError):
                q.put_nowait(frame)

    def close(self) -> None:
        """Stop background IPC polling worker."""
        self._running = False

    def _invoke_callback(self, cb: Callable[[EventFrame], Any], frame: EventFrame) -> None:
        try:
            if inspect.iscoroutinefunction(cb):
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(cb(frame))
                except RuntimeError:
                    # No running loop in current thread; run in fresh event loop
                    asyncio.run(cb(frame))
            else:
                res = cb(frame)
                if inspect.isawaitable(res):
                    try:
                        loop = asyncio.get_running_loop()
                        asyncio.ensure_future(res, loop=loop)
                    except RuntimeError:
                        asyncio.run(res)
        except (TypeError, ValueError, AttributeError, RuntimeError, KeyError, IndexError, OSError) as e:
            logger.warning("elastic.subscriber_callback_error", topic=frame.topic, error=str(e))

    def subscribe(
        self,
        pattern: str = "*",
        callback: Callable[[EventFrame], Any] | None = None,
        min_urgency: EventUrgency | str | None = None,
    ) -> str:
        """
        Subscribe to Elastic event topics.

        :param pattern: Topic pattern to match (e.g., '*', 'timer.*', 'system.*').
        :param callback: Callable function accepting an EventFrame.
        :param min_urgency: Minimum urgency threshold to receive events.
        :return: Subscription token string for unsubscription.
        """
        if callback is None:
            raise ValueError("Subscription callback cannot be None.")

        token = str(uuid.uuid4())[:8]
        parsed_min = EventUrgency.from_value(min_urgency) if min_urgency is not None else None

        sub = _Subscription(
            token=token,
            pattern=pattern.strip(),
            callback=callback,
            min_urgency=parsed_min,
        )

        with self._lock:
            self._subscriptions[token] = sub

        return token

    def unsubscribe(self, token: str) -> bool:
        """Cancel an active subscription by its token."""
        with self._lock:
            return self._subscriptions.pop(token, None) is not None

    async def stream(self, pattern: str = "*") -> AsyncIterator[EventFrame]:
        """
        Asynchronously stream EventFrames matching pattern.
        Ideal for SSE, WebSocket, and MCP notification pipes.
        """
        q: asyncio.Queue[EventFrame] = asyncio.Queue(maxsize=100)
        with self._lock:
            self._async_queues.append(q)

        try:
            while True:
                frame = await q.get()
                if pattern in ("*", frame.topic) or fnmatch.fnmatch(frame.topic, pattern):
                    yield frame
        finally:
            with self._lock:
                if q in self._async_queues:
                    self._async_queues.remove(q)

    # --- Tapestry Seat & Slot Management (Universal Blackboard Interface) ---

    def occupy_seat(
        self,
        slot: str,
        value: Any,
        *,
        summary: str = "",
        source: str = "system",
        urgency: EventUrgency | str = EventUrgency.AMBIENT,
    ) -> EventFrame:
        """
        Occupy / assign a seat (retained slot) on the Tapestry blackboard.
        Automatically updates the blackboard state and broadcasts the change event.

        :param slot: The slot / seat identifier (e.g. 'system.status', 'compositor.active_window').
        :param value: The state value to retain in the seat.
        :param summary: Optional human-readable description.
        :param source: The yarn or component name claiming the seat.
        :param urgency: Broadcast urgency tier (default AMBIENT).
        """
        clean_slot = slot.strip()
        thought = summary or f"Tapestry seat '{clean_slot}' occupied by {source}"
        return self.broadcast(
            topic=f"tapestry.seat.{clean_slot}",
            source=source,
            summary=thought,
            urgency=urgency,
            data={"slot": clean_slot, "value": value},
            retained_slot=clean_slot,
            retained_value=value,
        )

    def get_slot(self, slot: str, default: Any = None) -> Any:
        """Read a retained seat / slot from the Tapestry blackboard."""
        return sensory_tapestry.get_slot(slot, default)

    def get_state(self) -> dict[str, Any]:
        """Get full snapshot of the Tapestry blackboard state (slots and recent notices)."""
        return sensory_tapestry.get_state()


elastic = ElasticEngine()
