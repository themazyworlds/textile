"""
Textile Elastic - Unified Event Broadcast & Sensory Subscription Fabric.
Serves as the single front door for both broadcasting and subscribing to system events,
sensory deltas, and Tapestry state updates.
"""

import asyncio
import contextlib
import fnmatch
import inspect
import os
import threading
import time
import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from typing import Any

from needle import EventFrame, EventUrgency

lazy from textile.core.camshaft import camshaft
lazy from textile.core.tapestry.sensory import sensory_mesh as sensory_tapestry


@dataclass(slots=True)
class BroadcastOptions:
    source: str = "system"
    urgency: EventUrgency | str = EventUrgency.NOTICE
    data: dict[str, Any] | None = None
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

        if self.pattern in {"*", frame.topic}:
            return True

        return fnmatch.fnmatch(frame.topic, self.pattern)


class ElasticEngine:
    """
    Unified In-Process Event Hub & Sensory Routing Fabric.
    Provides reactive pubsub subscriptions, async streaming, and sensory state updates.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._pid = os.getpid()
        self._subscriptions: dict[str, _Subscription] = {}
        self._async_queues: set[asyncio.Queue[EventFrame]] = set()

    def broadcast(
        self,
        topic: str,
        summary: str,
        options: BroadcastOptions | str | None = None,
        **kwargs: Any,
    ) -> EventFrame:
        """
        Broadcast an event to all in-process subscribers, update retained slots, and stitch notices.

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
            camshaft.set_blackboard_slot(opts.retained_slot, opts.retained_value)

        # 2. Deliver in-process immediately (zero latency for local UI & listeners)
        self._deliver_local(frame)

        # 3. Stitch sensory notice for notice/alert/flash urgency levels
        if parsed_urgency in {EventUrgency.NOTICE, EventUrgency.ALERT, EventUrgency.FLASH}:
            notice_level = "INFO"
            if parsed_urgency == EventUrgency.FLASH:
                notice_level = "CRITICAL"
            elif parsed_urgency == EventUrgency.ALERT:
                notice_level = "WARNING"
            elif parsed_urgency == EventUrgency.NOTICE:
                notice_level = "NOTICE"

            with contextlib.suppress(Exception):
                camshaft.stitch_notice(
                    level=notice_level,
                    source=clean_source,
                    message=frame.summary,
                    data={"topic": clean_topic, "urgency": parsed_urgency.value} | payload_data,
                )

        return frame

    def _deliver_local(self, frame: EventFrame) -> None:
        """Deliver EventFrame to local in-process subscribers and async queues."""
        with self._lock:
            subs = list(self._subscriptions.values())
            queues = list(self._async_queues)

        for sub in subs:
            if sub.matches(frame):
                self._invoke_callback(sub.callback, frame)

        for q in queues:
            with contextlib.suppress(asyncio.QueueFull, RuntimeError):
                q.put_nowait(frame)

    def close(self) -> None:
        """Clear all active subscriptions and async queues."""
        with self._lock:
            self._subscriptions.clear()
            self._async_queues.clear()

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
            camshaft.stitch_notice(
                level="WARNING",
                source="elastic",
                message=f"Subscriber callback error for topic '{frame.topic}': {e}",
                data={"topic": frame.topic, "error": str(e)},
            )

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
            self._async_queues.add(q)

        try:
            while True:
                frame = await q.get()
                if pattern in {"*", frame.topic} or fnmatch.fnmatch(frame.topic, pattern):
                    yield frame
        finally:
            with self._lock:
                self._async_queues.discard(q)

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


@camshaft.on("strand_execution_started")
def _on_strand_started_broadcast(_sender: Any = None, **kwargs: Any) -> None:
    task_id = kwargs.get("task_id", "")
    strand_name = kwargs.get("strand_name", "")
    tier_val = kwargs.get("tier_val", "")
    caller = kwargs.get("caller", "")
    elastic.broadcast(
        topic="loom.tool_start",
        source="loom",
        summary=f"Starting strand '{strand_name}' [{tier_val.upper()}]",
        urgency=EventUrgency.AMBIENT,
        data={"task_id": task_id, "strand": strand_name, "caller": caller, "tier": tier_val},
    )


@camshaft.on("strand_executed")
def _on_strand_completed_broadcast(_sender: Any = None, **kwargs: Any) -> None:
    task_id = kwargs.get("task_id", "")
    strand_name = kwargs.get("strand_name", "")
    tier_val = kwargs.get("tier_val", "")
    caller = kwargs.get("caller", "")
    dur_ms = kwargs.get("duration_ms", 0.0)
    success = kwargs.get("success", False)
    err = kwargs.get("error")
    msg = (
        f"Executed '{strand_name}' [{tier_val.upper()}] ({dur_ms:.1f}ms)"
        if success
        else f"Failed '{strand_name}': {err}"
    )
    elastic.broadcast(
        topic="loom.tool_done",
        source="loom",
        summary=msg,
        urgency=EventUrgency.NOTICE if success else EventUrgency.ALERT,
        data={
            "task_id": task_id,
            "strand": strand_name,
            "success": success,
            "duration_ms": dur_ms,
            "caller": caller,
            "error": err,
        },
    )
