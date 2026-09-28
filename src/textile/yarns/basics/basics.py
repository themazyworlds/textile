import asyncio
import logging
import os
import subprocess
import sys
import time
import uuid
from typing import Any

from textile.core.base import Yarn, strand
from textile.core.seams import seams
from textile.core.shuttle import shuttle
from textile.core.tapestry import core_tapestry, sensory_tapestry
from textile.core.warp import WarpEvent, warp

logger = logging.getLogger(__name__)

ACTIVE_TIMERS: dict[str, dict[str, Any]] = {}


async def _timer_worker(timer_id: str, label: str, duration_seconds: float, end_time: float) -> None:
    try:
        sleep_dur = max(0.0, end_time - time.time())
        await asyncio.sleep(sleep_dur)
        ACTIVE_TIMERS.pop(timer_id, None)
        payload = {
            "id": timer_id,
            "label": label,
            "duration_seconds": duration_seconds,
            "expired_at": time.time(),
        }
        warp.publish(WarpEvent.TIMER_EXPIRED, payload)
        sensory_tapestry.stitch(
            level="info",
            source="basics",
            message=f"Timer '{label}' finished ({duration_seconds}s).",
            data=payload,
        )
    except asyncio.CancelledError:
        pass
    except (OSError, RuntimeError, ValueError) as e:
        logger.debug("Timer worker error on '%s': %s", timer_id, e)


class Basics(Yarn):
    """General System Timing & Integrity Basics Yarn."""

    def is_available(self) -> bool:
        return True

    @strand(tier="interact")
    async def set_timer(self, duration_seconds: float, label: str = "Timer") -> str:
        """Set a countdown timer that publishes an alert and notifies Weave when it expires.

        :param duration_seconds: Timer duration in seconds (e.g., 60 for 1 minute, 900 for 15 minutes).
        :param label: Descriptive label or reminder text (e.g., 'check oven', 'take a break').
        """
        dur = float(duration_seconds)
        if dur <= 0:
            return "Error: Timer duration must be greater than 0 seconds."

        clean_label = str(label or "Timer").strip()
        timer_id = str(uuid.uuid4())[:8]
        start_time = time.time()
        end_time = start_time + dur

        task = asyncio.create_task(_timer_worker(timer_id, clean_label, dur, end_time))
        ACTIVE_TIMERS[timer_id] = {
            "id": timer_id,
            "label": clean_label,
            "duration_seconds": dur,
            "start_time": start_time,
            "end_time": end_time,
            "task": task,
        }

        mins = int(dur // 60)
        secs = int(dur % 60)
        dur_str = f"{mins}m {secs}s" if mins > 0 else f"{secs}s"
        return f"Timer '{clean_label}' started for {dur_str} (ID: {timer_id})."

    @strand(tier="observe")
    def list_timers(self) -> list[dict[str, Any]]:
        """List all currently active countdown timers with remaining time."""
        now = time.time()
        timers = []
        for tid, info in list(ACTIVE_TIMERS.items()):
            remaining = max(0.0, round(info["end_time"] - now, 1))
            timers.append({
                "id": tid,
                "label": info["label"],
                "duration_seconds": info["duration_seconds"],
                "remaining_seconds": remaining,
            })
        return timers

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
        return f"Timer '{info['label']}' (ID: {found_id}) successfully cancelled."

    @strand(tier="observe")
    def shuttle_get_state(self) -> dict[str, Any]:
        """Get full snapshot of the Shuttle proactivity engine (curiosity level, tension map, inner monologue, quiet status)."""
        return shuttle.get_state()

    @strand(tier="mutate")
    def shuttle_set_quiet(self, duration_minutes: float = 15.0, permanent: bool = False) -> str:
        """Engage quiet mode to hold proactive voice speech for a duration (e.g. 15 minutes) or permanently.

        :param duration_minutes: Duration in minutes to suppress proactive voice speech (default 15.0).
        :param permanent: Set to true to mute proactive voice indefinitely until explicitly unmuted.
        """
        dur_secs = float(duration_minutes) * 60.0 if duration_minutes and not permanent else None
        return shuttle.set_quiet(duration_seconds=dur_secs, permanent=permanent)

    @strand(tier="mutate")
    def shuttle_unmute(self) -> str:
        """Unmute and resume proactive voice and ambient intervention alerts."""
        return shuttle.unmute()

    @strand(tier="observe")
    def textile_get_sensory_state(self) -> dict[str, Any]:
        """Get the open sensory blackboard snapshot (sensory state slots and recent stitched notices/alerts)."""
        return sensory_tapestry.get_state()

    @strand(tier="observe")
    def textile_get_state(self) -> dict[str, Any]:
        """Get full snapshot of the sensory blackboard state slots and notices."""
        return sensory_tapestry.get_state()

    @strand(tier="observe")
    def textile_get_engine_state(self) -> dict[str, Any]:
        """Get the core engine execution state (active running tasks and execution history)."""
        return core_tapestry.get_state()

    @strand(tier="mutate")
    def cancel_live_task(self, strand_name: str) -> str:
        """Cancel/terminate a currently running strand execution by its task ID or strand name.

        :param strand_name: The name or task ID of the running strand to cancel/terminate.
        """
        return core_tapestry.cancel_task(strand_name)

    @strand(tier="observe")
    def audit_yarn_integrity(self) -> dict[str, Any]:
        """Audit system-wide yarn health, runtime dependencies, layer overrides, and schemas."""
        return seams.audit_all()

    @strand(tier="privileged")
    def run_system_tests(self) -> str:
        """Run the full Textile system diagnostic unit, integration, and E2E test suite."""
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
        test_script = os.path.join(project_root, "tests", "run_all_tests.py")
        if not os.path.exists(test_script):
            return "Error: test script tests/run_all_tests.py not found."

        try:
            res = subprocess.run(
                [sys.executable, test_script],
                cwd=project_root,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=60,
                check=False,
            )
            return res.stdout
        except (OSError, subprocess.SubprocessError) as e:
            return f"Error executing system test suite: {e}"
