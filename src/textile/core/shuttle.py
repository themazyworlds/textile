"""
Textile Shuttle - Autonomous Proactivity & Ambient Cognition Engine.
Translates real-time Tapestry state deltas and Elastic events into spontaneous cognition,
tension resonance, curiosity drift, and governed desktop interventions.
"""

import datetime
import logging
import threading
import time
from typing import Any

from pydantic import BaseModel, Field

from textile.core.elastic import EventFrame, EventUrgency, elastic
from textile.core.tapestry import sensory_tapestry

logger = logging.getLogger(__name__)


class SparkPayload(BaseModel):
    """Represents a proactive resonance spark event triggered by tension or curiosity."""
    source: str
    reason: str
    is_flash: bool = False
    urgency: float = 0.8
    timestamp: str = Field(default_factory=lambda: datetime.datetime.now().isoformat())
    raw_data: Any = Field(default_factory=dict)
    inner_monologue: list[str] = Field(default_factory=list)
    suppressed_by_quiet: bool = False


class ShuttleState(BaseModel):
    """Full snapshot of Shuttle engine parameters and state."""
    enabled: bool = True
    quiet: bool = False
    quiet_remaining_seconds: float = 0.0
    curiosity_level: float = 0.0
    tension_map: dict[str, float] = Field(default_factory=dict)
    inner_monologue: list[str] = Field(default_factory=list)
    last_spark: SparkPayload | dict[str, Any] | None = None
    idle_seconds: float = 0.0


class ShuttleEngine:
    """
    Autonomous Proactive Cognition Engine.
    Manages two-speed tension resonance (Flash vs. Curiosity drift),
    inner monologue history, and the quiet/mute governor.
    """

    def __init__(
        self,
        spark_threshold: float = 0.8,
        decay_rate: float = 0.05,
        curiosity_drift_rate: float = 0.02,
        idle_timeout_seconds: float = 20.0,
    ):
        self.spark_threshold = spark_threshold
        self.decay_rate = decay_rate
        self.curiosity_drift_rate = curiosity_drift_rate
        self.idle_timeout_seconds = idle_timeout_seconds

        self._lock = threading.RLock()
        self._curiosity_level: float = 0.0
        self._tension_map: dict[str, float] = {}
        self._monologue_history: list[str] = []
        self._last_event_time: float = time.time()
        self._last_spark_time: float = time.time()
        self._initialized: bool = False
        self._sub_token: str | None = None

    def initialize(self) -> None:
        """Initialize engine, sync default Tapestry state slots, and subscribe to Elastic events."""
        with self._lock:
            if self._initialized:
                return

            if sensory_tapestry.get_slot("shuttle.enabled") is None:
                sensory_tapestry.set_slot("shuttle.enabled", True)
            if sensory_tapestry.get_slot("shuttle.quiet") is None:
                sensory_tapestry.set_slot("shuttle.quiet", False)
            if sensory_tapestry.get_slot("shuttle.curiosity_level") is None:
                sensory_tapestry.set_slot("shuttle.curiosity_level", 0.0)

            self._subscribe_elastic()
            self._initialized = True

    def _subscribe_elastic(self) -> None:
        """Attach automatic event listeners to the Elastic event bus."""

        def _on_elastic_event(frame: EventFrame) -> None:
            src = frame.source
            if (
                src in ("shuttle", "weave", "voice", "canvas", "canvas_weft")
                or src.startswith("shuttle.")
                or frame.topic in ("voice.state", "canvas.mood", "loom.tool_start")
            ):
                return

            if frame.topic == "loom.tool_done":
                data = frame.data
                s_name = data.get("strand", "tool")
                if s_name.startswith("shuttle_") or s_name == "shuttle":
                    return
                success = data.get("success", True)
                err = data.get("error")
                if not success:
                    self.feed_event(
                        source=f"tool.{s_name}",
                        event_type="tool_failure",
                        data=data,
                        urgency=0.4,
                        summary=f"Tool '{s_name}' execution failed: {err}",
                    )
                else:
                    self.feed_event(
                        source=f"tool.{s_name}",
                        event_type="tool_success",
                        data=data,
                        urgency=0.1,
                        summary=f"Executed tool '{s_name}' successfully",
                    )
                return

            is_critical = (
                frame.urgency in (EventUrgency.ALERT, EventUrgency.FLASH)
                or "crash" in frame.summary.lower()
                or "error" in frame.summary.lower()
            )
            if is_critical:
                self.feed_event(
                    source=f"event.{src}",
                    event_type="alert",
                    data=frame.data,
                    urgency=1.0 if frame.urgency == EventUrgency.FLASH else 0.8,
                    summary=frame.summary or f"Critical event from {src}",
                )
            else:
                self.feed_event(
                    source=f"event.{src}",
                    event_type="notice",
                    data=frame.data,
                    urgency=0.2,
                    summary=frame.summary or f"Event '{frame.topic}' from {src}",
                )

        self._sub_token = elastic.subscribe("*", _on_elastic_event)

    def close(self) -> None:
        """Unsubscribe from Elastic event bus and clear subscriptions."""
        with self._lock:
            if self._sub_token:
                elastic.unsubscribe(self._sub_token)
                self._sub_token = None
            self._initialized = False

    # --- Governor Controls ---

    def is_enabled(self) -> bool:
        return bool(sensory_tapestry.get_slot("shuttle.enabled", True))

    def set_enabled(self, enabled: bool) -> None:
        sensory_tapestry.set_slot("shuttle.enabled", bool(enabled))

    def is_quiet(self) -> bool:
        """Check if proactivity voice alerts are currently muted."""
        with self._lock:
            if sensory_tapestry.get_slot("shuttle.quiet", False):
                return True

            quiet_until = sensory_tapestry.get_slot("shuttle.quiet_until")
            if quiet_until:
                try:
                    ts = float(quiet_until)
                    if time.time() < ts:
                        return True
                    else:
                        sensory_tapestry.set_slot("shuttle.quiet_until", None)
                        elastic.broadcast(
                            topic="shuttle.quiet_changed",
                            source="shuttle",
                            summary="Shuttle quiet mode expired",
                            urgency=EventUrgency.NOTICE,
                            data={"quiet": False, "reason": "expired"},
                            retained_slot="shuttle.quiet",
                            retained_value=False,
                        )
                except (ValueError, TypeError):
                    sensory_tapestry.set_slot("shuttle.quiet_until", None)

            return False

    def set_quiet(self, duration_seconds: float | None = None, permanent: bool = False) -> str:
        """Engage quiet mode for a specific duration or permanently."""
        with self._lock:
            if permanent or duration_seconds is None or duration_seconds <= 0:
                sensory_tapestry.set_slot("shuttle.quiet", True)
                sensory_tapestry.set_slot("shuttle.quiet_until", None)
                elastic.broadcast(
                    topic="shuttle.quiet_changed",
                    source="shuttle",
                    summary="Shuttle quiet mode enabled indefinitely",
                    urgency=EventUrgency.NOTICE,
                    data={"quiet": True, "permanent": True},
                    retained_slot="shuttle.quiet",
                    retained_value=True,
                )
                return "Shuttle quiet mode enabled indefinitely (unmute anytime with shuttle_unmute)."
            else:
                until_ts = time.time() + float(duration_seconds)
                sensory_tapestry.set_slot("shuttle.quiet", False)
                sensory_tapestry.set_slot("shuttle.quiet_until", until_ts)
                mins = round(duration_seconds / 60, 1)
                elastic.broadcast(
                    topic="shuttle.quiet_changed",
                    source="shuttle",
                    summary=f"Shuttle quiet mode enabled for {mins} minutes",
                    urgency=EventUrgency.NOTICE,
                    data={"quiet": True, "until": until_ts, "duration_seconds": duration_seconds},
                    retained_slot="shuttle.quiet",
                    retained_value=True,
                )
                return f"Shuttle quiet mode enabled for {mins} minutes."

    def unmute(self) -> str:
        """Clear quiet mode and resume normal proactivity."""
        with self._lock:
            sensory_tapestry.set_slot("shuttle.quiet", False)
            sensory_tapestry.set_slot("shuttle.quiet_until", None)
            elastic.broadcast(
                topic="shuttle.quiet_changed",
                source="shuttle",
                summary="Shuttle quiet mode unmuted",
                urgency=EventUrgency.NOTICE,
                data={"quiet": False, "reason": "manual_unmute"},
                retained_slot="shuttle.quiet",
                retained_value=False,
            )
            return "Shuttle proactivity unmuted and active."

    # --- Tension, Curiosity & Monologue ---

    @property
    def curiosity_level(self) -> float:
        with self._lock:
            return round(self._curiosity_level, 3)

    def feed_event(
        self,
        source: str,
        event_type: str,
        data: Any,
        urgency: float = 0.2,
        summary: str = "",
    ) -> dict[str, Any] | None:
        """
        Feed a sensory event into the proactivity engine.
        Accumulates tension, updates inner monologue, and fires sparks when thresholds are crossed.
        """
        with self._lock:
            now = time.time()
            self._last_event_time = now
            src_clean = str(source).strip()

            thought_text = summary or f"[{src_clean}] Event {event_type}"
            ts_str = datetime.datetime.now().strftime("%H:%M:%S")
            monologue_entry = f"{ts_str} - {thought_text}"
            self._monologue_history.append(monologue_entry)
            if len(self._monologue_history) > 20:
                self._monologue_history.pop(0)

            sensory_tapestry.set_slot("shuttle.inner_monologue", list(self._monologue_history))

            # 1. Flash Track (Instant Trigger)
            if urgency >= 1.0:
                return self._fire_spark(
                    source=src_clean,
                    reason=thought_text,
                    data=data,
                    is_flash=True,
                    urgency=1.0,
                )

            # 2. Curiosity & Compounding Tension Track
            current_tension = self._tension_map.get(src_clean, 0.0)
            new_tension = min(1.0, current_tension + urgency)
            self._tension_map[src_clean] = new_tension

            self._curiosity_level = min(1.0, self._curiosity_level + urgency * 0.4)
            sensory_tapestry.set_slot("shuttle.curiosity_level", round(self._curiosity_level, 3))

            if new_tension >= self.spark_threshold or self._curiosity_level >= self.spark_threshold:
                return self._fire_spark(
                    source=src_clean,
                    reason=f"Compounding tension on '{src_clean}' reached resonance ({round(new_tension, 2)})",
                    data=data,
                    is_flash=False,
                    urgency=new_tension,
                )

            return None

    def tick(self, delta_seconds: float = 1.0) -> dict[str, Any] | None:
        """
        Periodic engine evaluation tick (runs every ~1 second).
        Applies half-life tension decay and curiosity drift during inactivity.
        """
        with self._lock:
            now = time.time()
            idle_duration = now - self._last_event_time

            for src in list(self._tension_map.keys()):
                val = self._tension_map[src] - self.decay_rate * delta_seconds
                if val <= 0.01:
                    self._tension_map.pop(src, None)
                else:
                    self._tension_map[src] = round(val, 4)

            if idle_duration >= self.idle_timeout_seconds:
                self._curiosity_level = min(1.0, self._curiosity_level + self.curiosity_drift_rate * delta_seconds)
                sensory_tapestry.set_slot("shuttle.curiosity_level", round(self._curiosity_level, 3))

                if self._curiosity_level >= self.spark_threshold and (now - self._last_spark_time) > 60.0:
                    return self._fire_spark(
                        source="idle_curiosity",
                        reason=f"Curiosity drift peak after {int(idle_duration)}s of desktop silence",
                        data={"idle_seconds": round(idle_duration, 1)},
                        is_flash=False,
                        urgency=round(self._curiosity_level, 2),
                    )

            sensory_tapestry.set_slot("shuttle.curiosity_level", round(self._curiosity_level, 3))
            return None

    def _fire_spark(
        self,
        source: str,
        reason: str,
        data: Any,
        is_flash: bool = False,
        urgency: float = 0.8,
    ) -> dict[str, Any]:
        """Fire a proactive resonance spark."""
        now = time.time()
        self._last_spark_time = now
        self._tension_map.pop(source, None)
        self._curiosity_level = max(0.0, self._curiosity_level - 0.5)

        spark_model = SparkPayload(
            source=source,
            reason=reason,
            is_flash=is_flash,
            urgency=urgency,
            timestamp=datetime.datetime.now().isoformat(),
            raw_data=data if isinstance(data, (dict, list, str, int, float, bool)) else str(data),
            inner_monologue=list(self._monologue_history[-5:]),
            suppressed_by_quiet=self.is_quiet(),
        )
        spark_payload = spark_model.model_dump()

        sensory_tapestry.set_slot("shuttle.last_spark", spark_payload)
        sensory_tapestry.set_slot("shuttle.curiosity_level", round(self._curiosity_level, 3))

        if not self.is_enabled():
            return spark_payload

        if self.is_quiet() and not is_flash:
            sensory_tapestry.stitch(
                level="debug",
                source="shuttle",
                message=f"Proactive voice spark suppressed by quiet mode: {reason}",
                data=spark_payload,
            )
            return spark_payload

        elastic.broadcast(
            topic="shuttle.spark",
            source="shuttle",
            summary=f"Proactive Spark ({'FLASH' if is_flash else 'RESONANCE'}): {reason}",
            urgency=EventUrgency.FLASH if is_flash else EventUrgency.ALERT,
            data=spark_payload,
            retained_slot="shuttle.last_spark",
            retained_value=spark_payload,
        )
        sensory_tapestry.stitch(
            level="info" if is_flash else "notice",
            source="shuttle",
            message=f"Proactive Spark ({'FLASH' if is_flash else 'RESONANCE'}): {reason}",
            data=spark_payload,
        )
        return spark_payload

    def get_state(self) -> dict[str, Any]:
        """Get full snapshot of Shuttle engine parameters and state."""
        with self._lock:
            now = time.time()
            quiet_until = sensory_tapestry.get_slot("shuttle.quiet_until")
            remaining_quiet = 0.0
            if quiet_until:
                try:
                    remaining_quiet = max(0.0, round(float(quiet_until) - now, 1))
                except (ValueError, TypeError):
                    pass

            state = ShuttleState(
                enabled=self.is_enabled(),
                quiet=self.is_quiet(),
                quiet_remaining_seconds=remaining_quiet,
                curiosity_level=self.curiosity_level,
                tension_map=dict(self._tension_map),
                inner_monologue=list(self._monologue_history),
                last_spark=sensory_tapestry.get_slot("shuttle.last_spark"),
                idle_seconds=round(now - self._last_event_time, 1),
            )
            return state.model_dump()


shuttle = ShuttleEngine()
