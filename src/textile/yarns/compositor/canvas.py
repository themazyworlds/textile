"""
Textile Quickshell Canvas UI & Dynamic Mood Subsystem Yarn.
Provides real-time emotive expression, mood orchestration, and IPC control over the interactive desktop canvas.
Layer 100 (Compositor / DE).
"""

import json
import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from textile.core.base import BaseYarn, strand, weft, LAYER_COMPOSITOR_DE
from textile.core.tapestry import tapestry
from textile.core.warp import WarpEvent

logger = logging.getLogger(__name__)


def _get_qml_path() -> str:
    """Return the absolute path to the Canvas QML interface inside the yarn module."""
    curr_dir = Path(__file__).resolve().parent
    qml_file = curr_dir / "canvas.qml"
    if qml_file.exists():
        return str(qml_file)
    fallback = curr_dir / "shell.qml"
    if fallback.exists():
        return str(fallback)
    return str(Path(__file__).resolve().parent.parent.parent / "ui" / "canvas" / "shell.qml")


class CanvasController:
    """Controller for Quickshell Canvas subprocess and IPC."""

    def __init__(self):
        self._proc: Optional[subprocess.Popen] = None

    def get_qml_path(self) -> str:
        return _get_qml_path()

    def is_running(self) -> bool:
        if self._proc is not None:
            if self._proc.poll() is None:
                return True
            self._proc = None
        qml_file = self.get_qml_path()
        try:
            res = subprocess.run(["pgrep", "-f", qml_file], capture_output=True, timeout=0.2)
            if res.returncode == 0 and res.stdout.strip():
                return True
        except Exception:
            pass
        return bool(tapestry.get_slot("canvas.visible", False))

    def launch(self) -> str:
        """Launch the Quickshell Canvas window."""
        qml_file = self.get_qml_path()
        if not os.path.exists(qml_file):
            return f"Error: QML file not found at {qml_file}"

        if self.is_running():
            tapestry.set_slot("canvas.visible", True)
            return "Canvas is already running."

        try:
            self._proc = subprocess.Popen(
                ["quickshell", "-p", qml_file],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            tapestry.set_slot("canvas.visible", True)
            tapestry.set_slot("canvas.pid", self._proc.pid)
            tapestry.stitch("INFO", "canvas", f"Canvas UI launched (PID {self._proc.pid})")
            return f"Canvas UI launched (PID {self._proc.pid})."
        except Exception as e:
            return f"Error launching canvas UI: {e}"

    def close(self) -> str:
        """Close the Quickshell Canvas window."""
        import time
        self.call_ipc("quit")
        qml_file = self.get_qml_path()

        time.sleep(0.15)

        if self._proc is not None:
            try:
                self._proc.terminate()
                self._proc.wait(timeout=1)
            except Exception:
                try:
                    self._proc.kill()
                except Exception:
                    pass
            self._proc = None

        try:
            subprocess.run(["pkill", "-f", qml_file], capture_output=True, timeout=2)
        except Exception:
            pass

        tapestry.set_slot("canvas.visible", False)
        tapestry.set_slot("canvas.pid", None)
        return "Canvas UI closed."

    def call_ipc(self, method: str, *args: Any, wait: bool = False) -> str:
        """Execute a Quickshell IPC call to the canvas target."""
        qml_file = self.get_qml_path()
        str_args = [str(a) for a in args]
        cmd = ["quickshell", "-p", qml_file, "ipc", "call", "canvas", method, *str_args]

        # Queries (like getState, getMood) or explicit wait requests block for stdout
        if wait or method in ("getState", "getMood"):
            try:
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=0.8)
                out = res.stdout.strip()
                if res.returncode != 0 and res.stderr:
                    return f"IPC Error: {res.stderr.strip()}"
                return out or "OK"
            except subprocess.TimeoutExpired:
                return "Error: IPC call timed out."
            except Exception as e:
                return f"Error calling Canvas IPC: {e}"

        # Fast one-way UI updates (setMood, setGaze, setTalking, triggerRipple) fire non-blocking
        try:
            subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=False,
            )
            return "OK"
        except Exception as e:
            return f"Error dispatching Canvas IPC: {e}"


canvas_ctl = CanvasController()


class Canvas(BaseYarn):
    """Quickshell Emotive Canvas & Mood System Yarn.

    The Canvas avatar is your physical, visual face on the Linux desktop.
    ALWAYS interleave rich semantic mood and gaze tags frequently throughout your speech stream to reflect your inner thought processes, reactions, and conversational turns in real-time.
    Available semantic tags:
    - Mood tags: <mood:neutral>, <mood:happy>, <mood:excited>, <mood:celebrating>, <mood:thinking>, <mood:focused>, <mood:listening>, <mood:curious>, <mood:calm>, <mood:shy>, <mood:mischievous>, <mood:confused>, <mood:surprised>, <mood:alert>, <mood:sleepy>, <mood:error>, <mood:glitch>
    - Gaze tags: <gaze:X,Y> (where X is -16.0 to 16.0, Y is -12.0 to 12.0)

    Frequent multi-tag usage in a single turn (2 to 4 tags per sentence/response) makes your avatar exceptionally fluid, expressive, and alive (e.g., "<mood:curious> Let's see what you need... <mood:thinking> checking workspace now... <mood:happy> Done!").
    """

    name = "canvas"
    description = "Textile Quickshell Canvas UI, Dynamic Mood Controller, and Expression Engine. Use frequent inline <mood:...> and <gaze:X,Y> tags in speech stream."
    version = "1.0.0"
    layer = LAYER_COMPOSITOR_DE  # Layer 100

    def is_available(self) -> bool:
        return bool(shutil.which("quickshell") or shutil.which("qs"))

    def on_load(self) -> None:
        from textile.core.warp import WarpEvent

        def _on_tool_start(data: Any) -> None:
            event = data if isinstance(data, dict) else {}
            caller = event.get("caller", "")
            strand = event.get("strand", "")
            # Ignore internal Canvas UI strands and passive state inspections
            if strand.startswith("canvas_") or strand.startswith("textile_get_"):
                return
            # The forehead gemstone only ripples when an actual system/agent tool task is channeled by Weave
            if caller == "weave":
                canvas_ctl.call_ipc("triggerRipple")

        def _on_mood_change(data: Any) -> None:
            event = data if isinstance(data, dict) else {}
            source = event.get("source", "")
            mood = str(event.get("mood", "neutral") if isinstance(data, dict) else data).lower().strip()
            self.set_slot("canvas.mood", mood)
            if source != "canvas_weft":
                canvas_ctl.call_ipc("setMood", mood)

        def _on_voice_state(data: Any) -> None:
            event = data if isinstance(data, dict) else {}
            if "talking" in event:
                talking = bool(event["talking"])
                self.set_slot("canvas.is_talking", talking)
                canvas_ctl.call_ipc("setTalking", "true" if talking else "false")
            if "listening" in event:
                listening = bool(event["listening"])
                self.set_slot("canvas.is_listening", listening)
                canvas_ctl.call_ipc("setListening", "true" if listening else "false")

        self._on_tool_start = _on_tool_start
        self._on_mood_change = _on_mood_change
        self._on_voice_state = _on_voice_state

        self.warp.subscribe(WarpEvent.TOOL_EXECUTION_START, self._on_tool_start)
        self.warp.subscribe(WarpEvent.MOOD_CHANGE, self._on_mood_change)
        self.warp.subscribe(WarpEvent.VOICE_STATE, self._on_voice_state)

        # Auto-launch Canvas UI window when yarn is active and available (unless in test suite)
        if not os.environ.get("TEXTILE_TESTING") and not os.environ.get("PYTEST_CURRENT_TEST"):
            if self.is_available() and not canvas_ctl.is_running():
                canvas_ctl.launch()

    def on_unload(self) -> None:
        from textile.core.warp import WarpEvent
        if hasattr(self, "_on_tool_start"):
            self.warp.unsubscribe(WarpEvent.TOOL_EXECUTION_START, self._on_tool_start)
        if hasattr(self, "_on_mood_change"):
            self.warp.unsubscribe(WarpEvent.MOOD_CHANGE, self._on_mood_change)
        if hasattr(self, "_on_voice_state"):
            self.warp.unsubscribe(WarpEvent.VOICE_STATE, self._on_voice_state)
        # Close canvas on yarn unload / disable
        if canvas_ctl.is_running():
            canvas_ctl.close()

    @weft(pattern=r"<mood:([a-zA-Z_-]+)>", description="Stream attunement for dynamic mood changes. Emit frequent inline tags (e.g. <mood:curious>, <mood:thinking>, <mood:happy>, <mood:excited>, <mood:focused>, <mood:shy>, <mood:mischievous>, <mood:neutral>) across your spoken sentences to animate the avatar face in real time.")
    def on_stream_mood(self, mood: str) -> None:
        """Handle real-time streaming mood attunement from speech/transcription."""
        clean_mood = mood.lower().strip()
        self.set_slot("canvas.mood", clean_mood)
        self.publish_event(WarpEvent.MOOD_CHANGE, {"mood": clean_mood, "source": "canvas_weft"})
        canvas_ctl.call_ipc("setMood", clean_mood)

    @weft(pattern=r"<gaze:(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)>", description="Stream attunement for dynamic eye gaze offsets (e.g. <gaze:8.0,-5.0> to look up-right, <gaze:-10.0,0.0> to glance left).")
    def on_stream_gaze(self, x: float, y: float) -> None:
        """Handle real-time streaming eye gaze attunement."""
        canvas_ctl.call_ipc("setGaze", str(x), str(y))

    @strand(description="Launch the Quickshell Canvas UI window.")
    def canvas_launch(self) -> str:
        """Launch the Quickshell Canvas UI window."""
        return canvas_ctl.launch()

    @strand(description="Close the Quickshell Canvas UI window.")
    def canvas_close(self) -> str:
        """Close the Quickshell Canvas UI window."""
        return canvas_ctl.close()

    @strand(description="Set canvas mood (neutral, happy, excited, celebrating, thinking, focused, listening, curious, calm, shy, mischievous, confused, surprised, alert, sleepy, error, glitch).")
    def canvas_set_mood(self, mood: str = "neutral") -> str:
        """Set canvas mood.

        :param mood: Desired mood (e.g. 'neutral', 'happy', 'excited', 'celebrating', 'thinking', 'focused', 'listening', 'curious', 'calm', 'shy', 'mischievous', 'confused', 'surprised', 'alert', 'sleepy', 'error', 'glitch').
        """
        clean_mood = mood.lower().strip()
        self.set_slot("canvas.mood", clean_mood)
        res = canvas_ctl.call_ipc("setMood", clean_mood)
        return f"Mood set to '{clean_mood}' ({res})"

    @strand(description="Set canvas fine-grained expression state.")
    def canvas_set_expression(self, expression: str = "neutral") -> str:
        """Set canvas fine-grained expression state.

        :param expression: Expression name (e.g. 'neutral', 'smile', 'frown', 'blink', 'wide_eyes').
        """
        clean_expr = expression.lower().strip()
        self.set_slot("canvas.expression", clean_expr)
        res = canvas_ctl.call_ipc("setExpression", clean_expr)
        return f"Expression set to '{clean_expr}' ({res})"

    @strand(description="Toggle canvas speaking/talking mouth animation.")
    def canvas_set_talking(self, talking: bool = True) -> str:
        """Toggle canvas speaking/talking mouth animation.

        :param talking: True to animate speaking mouth, False to stop.
        """
        self.set_slot("canvas.is_talking", talking)
        res = canvas_ctl.call_ipc("setTalking", "true" if talking else "false")
        return f"Talking animation set to {talking} ({res})"

    @strand(description="Toggle canvas listening visual state.")
    def canvas_set_listening(self, listening: bool = True) -> str:
        """Toggle canvas listening visual state.

        :param listening: True when the agent or assistant is actively listening to audio.
        """
        self.set_slot("canvas.is_listening", listening)
        res = canvas_ctl.call_ipc("setListening", "true" if listening else "false")
        return f"Listening state set to {listening} ({res})"

    @strand(description="Set manual canvas eye gaze offsets.")
    def canvas_set_gaze(self, x: float = 0.0, y: float = 0.0) -> str:
        """Set manual canvas eye gaze offsets.

        :param x: Horizontal gaze offset (-14.0 to 14.0).
        :param y: Vertical gaze offset (-10.0 to 10.0).
        """
        res = canvas_ctl.call_ipc("setGaze", str(x), str(y))
        return f"Gaze set to ({x}, {y}) ({res})"

    @strand(description="Reset canvas eye gaze to cursor tracking.")
    def canvas_reset_gaze(self) -> str:
        """Reset canvas eye gaze to cursor tracking."""
        res = canvas_ctl.call_ipc("resetGaze")
        return f"Gaze reset to cursor tracking ({res})"

    @strand(description="Customize canvas face feature and background colors.")
    def canvas_set_color(self, feature_color: str = "", bg_color: str = "") -> str:
        """Customize canvas face feature and background colors.

        :param feature_color: Hex or CSS color string for features (e.g. '#fab387', '#a6e3a1').
        :param bg_color: Hex or CSS color string for canvas background (e.g. '#181825').
        """
        res = canvas_ctl.call_ipc("setColor", feature_color, bg_color)
        return f"Canvas colors updated ({res})"

    @strand(description="Get full real-time mood and canvas face state.")
    def canvas_get_state(self) -> Dict[str, Any]:
        """Get full real-time mood and canvas face state."""
        state = {
            "mood": self.get_slot("canvas.mood", "neutral"),
            "expression": self.get_slot("canvas.expression", "neutral"),
            "is_talking": self.get_slot("canvas.is_talking", False),
            "is_listening": self.get_slot("canvas.is_listening", False),
            "canvas_visible": self.get_slot("canvas.visible", False),
            "canvas_pid": self.get_slot("canvas.pid", None),
            "is_running": canvas_ctl.is_running(),
        }
        if state["is_running"]:
            ipc_res = canvas_ctl.call_ipc("getState")
            if ipc_res and ipc_res.startswith("{"):
                try:
                    qml_state = json.loads(ipc_res)
                    state.update(qml_state)
                    state["is_running"] = True
                except Exception:
                    pass
        return state
