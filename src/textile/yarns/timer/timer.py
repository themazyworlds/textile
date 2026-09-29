"""
Textile Timer Yarn - Countdown timers, reminder alerts, and scheduled notifications.
Layer 10 (Core POSIX / Utilities).
"""

import asyncio
import logging
import time
import uuid
from typing import Any

from textile import Yarn, strand
from textile.core.elastic import EventUrgency, elastic

logger = logging.getLogger(__name__)

ACTIVE_TIMERS: dict[str, dict[str, Any]] = {}


def _get_active_timers_snapshot() -> list[dict[str, Any]]:
    """Return live snapshot of active timers with remaining time calculated."""
    now = time.time()
    timers = []
    for tid, info in list(ACTIVE_TIMERS.items()):
        remaining = max(0.0, round(info["end_time"] - now, 1))
        timers.append(
            {
                "id": tid,
                "label": info["label"],
                "duration_seconds": info["duration_seconds"],
                "remaining_seconds": remaining,
                "start_time": info["start_time"],
                "end_time": info["end_time"],
            }
        )
    return timers


async def _timer_worker(timer_id: str, label: str, duration_seconds: float, end_time: float) -> None:
    try:
        sleep_dur = max(0.0, end_time - time.time())
        await asyncio.sleep(sleep_dur)
        ACTIVE_TIMERS.pop(timer_id, None)
        active_left = _get_active_timers_snapshot()
        payload = {
            "id": timer_id,
            "label": label,
            "duration_seconds": duration_seconds,
            "expired_at": time.time(),
        }
        elastic.broadcast(
            topic="timer.expired",
            source="timer",
            summary=f"Timer '{label}' (ID: {timer_id}) finished ({duration_seconds}s).",
            urgency=EventUrgency.ALERT,
            data=payload,
            retained_slot="timers.active",
            retained_value=active_left,
        )
    except asyncio.CancelledError:
        pass
    except (OSError, RuntimeError, ValueError) as e:
        logger.debug("Timer worker error on '%s': %s", timer_id, e)


class Timer(Yarn):
    """Countdown Timer and Reminder Alerts Yarn."""

    def is_available(self) -> bool:
        return True

    @strand(tier="interact")
    async def set_timer(self, duration_seconds: float, label: str = "Timer", timer_id: str | None = None) -> str:
        """Set a countdown timer that publishes an alert when it expires.

        :param duration_seconds: Timer duration in seconds (e.g., 60 for 1 minute, 900 for 15 minutes).
        :param label: Descriptive label or reminder text (e.g., 'check oven', 'take a break').
        :param timer_id: Optional custom identifier for the timer (auto-generated if omitted).
        """
        dur = float(duration_seconds)
        if dur <= 0:
            return "Error: Timer duration must be greater than 0 seconds."

        clean_label = str(label or "Timer").strip()
        tid = str(timer_id or "").strip() or str(uuid.uuid4())[:8]
        if tid in ACTIVE_TIMERS:
            tid = f"{tid}-{str(uuid.uuid4())[:4]}"

        start_time = time.time()
        end_time = start_time + dur

        task = asyncio.create_task(_timer_worker(tid, clean_label, dur, end_time))
        ACTIVE_TIMERS[tid] = {
            "id": tid,
            "label": clean_label,
            "duration_seconds": dur,
            "start_time": start_time,
            "end_time": end_time,
            "task": task,
        }

        mins = int(dur // 60)
        secs = int(dur % 60)
        dur_str = f"{mins}m {secs}s" if mins > 0 else f"{secs}s"

        active_snap = _get_active_timers_snapshot()
        elastic.broadcast(
            topic="timer.started",
            source="timer",
            summary=f"Timer '{clean_label}' started for {dur_str} (ID: {tid}).",
            urgency=EventUrgency.NOTICE,
            data={"id": tid, "label": clean_label, "duration_seconds": dur, "end_time": end_time},
            retained_slot="timers.active",
            retained_value=active_snap,
        )
        return f"Timer '{clean_label}' started for {dur_str} (ID: {tid})."

    @strand(tier="observe")
    def list_timers(self) -> list[dict[str, Any]]:
        """List all currently active countdown timers with remaining time."""
        return _get_active_timers_snapshot()

    @strand(tier="mutate")
    def cancel_timer(self, timer_id: str) -> str:
        """Cancel a running countdown timer by its timer ID or label.

        :param timer_id: The ID or label of the timer to cancel.
        """
        clean_target = str(timer_id or "").strip()
        found_id = None
        if clean_target in ACTIVE_TIMERS:
            found_id = clean_target
        else:
            for tid, info in list(ACTIVE_TIMERS.items()):
                if info["label"].lower() == clean_target.lower():
                    found_id = tid
                    break

        if not found_id or found_id not in ACTIVE_TIMERS:
            return f"Error: No active timer found matching '{clean_target}'."

        info = ACTIVE_TIMERS.pop(found_id)
        task = info.get("task")
        if task and not task.done():
            task.cancel()

        active_left = _get_active_timers_snapshot()
        elastic.broadcast(
            topic="timer.cancelled",
            source="timer",
            summary=f"Timer '{info['label']}' (ID: {found_id}) cancelled.",
            urgency=EventUrgency.NOTICE,
            data={"id": found_id, "label": info["label"]},
            retained_slot="timers.active",
            retained_value=active_left,
        )
        return f"Timer '{info['label']}' (ID: {found_id}) successfully cancelled."
