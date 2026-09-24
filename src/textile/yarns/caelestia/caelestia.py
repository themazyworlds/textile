"""
Caelestia Shell and Quickshell IPC Capability Yarn.
Layer 100 (Compositor / DE).
"""

import shutil
import subprocess

from textile.core.base import Yarn, strand


class CaelestiaIPC:
    """Caelestia Shell IPC Controller."""

    def call_ipc(self, target: str, method: str, *args: str) -> str:
        qs_bin = shutil.which("qs") or "qs"
        cmd = [qs_bin, "-c", "caelestia", "ipc", "call", target, method, *args]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=5, check=False)
            return res.stdout.strip()
        except (OSError, subprocess.SubprocessError) as e:
            return f"Error calling Caelestia IPC: {e}"

    def toggle_drawer(self, drawer: str) -> str:
        d_clean = drawer.lower().strip()
        self.call_ipc("drawers", "toggle", d_clean)
        return f"Toggled Caelestia drawer: {d_clean}"

    def toggle_special(self, workspace: str) -> str:
        ws_clean = workspace.lower().strip()
        bin_path = shutil.which("caelestia") or "caelestia"
        try:
            subprocess.run([bin_path, "toggle", ws_clean], capture_output=True, text=True, timeout=5, check=False)
            return f"Toggled special workspace: {ws_clean}"
        except (OSError, subprocess.SubprocessError) as e:
            return f"Error toggling special workspace: {e}"

    def clear_notifications(self) -> str:
        self.call_ipc("notifs", "clear")
        return "Cleared all Caelestia notifications."

    def toggle_dnd(self) -> str:
        self.call_ipc("notifs", "toggleDnd")
        return "Toggled Do Not Disturb."

    def lock_screen(self) -> str:
        self.call_ipc("lock", "lock")
        return "Locked screen."

    def screenshot(self) -> str:
        bin_path = shutil.which("caelestia") or "caelestia"
        try:
            subprocess.Popen([bin_path, "screenshot"])
            return "Screenshot tool launched."
        except (OSError, subprocess.SubprocessError) as e:
            return f"Error taking screenshot: {e}"

    def record(self, audio: bool = False, region: bool = False) -> str:
        bin_path = shutil.which("caelestia") or "caelestia"
        args = [bin_path, "record"]
        if audio:
            args.append("-s")
        if region:
            args.append("-r")
        try:
            subprocess.Popen(args)
            return "Screen recording triggered."
        except (OSError, subprocess.SubprocessError) as e:
            return f"Error starting recording: {e}"


caelestia_ipc = CaelestiaIPC()


class Caelestia(Yarn):
    def is_available(self) -> bool:
        return bool(shutil.which("caelestia") or shutil.which("qs"))

    @strand(
        description="Toggle Caelestia UI drawer (launcher, sidebar, session, dashboard, etc.).",
        tier="interact",
    )
    def caelestia_toggle_drawer(self, drawer: str = "launcher") -> str:
        """Toggle Caelestia UI drawer (launcher, sidebar, session, dashboard, etc.).

        :param drawer: Drawer name (e.g. 'launcher', 'sidebar', 'session', 'dashboard').
        """
        return caelestia_ipc.toggle_drawer(drawer or "launcher")

    @strand(
        description="Toggle Caelestia special overlay workspace (sysmon, music, todo, etc.).",
        tier="interact",
    )
    def caelestia_toggle_special_workspace(self, workspace: str = "sysmon") -> str:
        """Toggle Caelestia special overlay workspace (sysmon, music, todo, etc.).

        :param workspace: Special workspace name (e.g. 'sysmon', 'music', 'todo').
        """
        return caelestia_ipc.toggle_special(workspace or "sysmon")

    @strand(description="Clear all active Caelestia shell notifications.", tier="interact")
    def caelestia_clear_notifications(self) -> str:
        """Clear all active Caelestia shell notifications."""
        return caelestia_ipc.clear_notifications()

    @strand(description="Toggle Do Not Disturb mode for Caelestia notifications.", tier="interact")
    def caelestia_toggle_dnd(self) -> str:
        """Toggle Do Not Disturb mode for Caelestia notifications."""
        return caelestia_ipc.toggle_dnd()

    @strand(description="Lock desktop screen via Caelestia lock controller.", tier="interact")
    def caelestia_lock_screen(self) -> str:
        """Lock desktop screen via Caelestia lock controller."""
        return caelestia_ipc.lock_screen()

    @strand(description="Launch Caelestia interactive screenshot tool.", tier="interact")
    def caelestia_take_screenshot(self) -> str:
        """Launch Caelestia interactive screenshot tool."""
        return caelestia_ipc.screenshot()

    @strand(description="Trigger Caelestia screen recording.", tier="interact")
    def caelestia_record_screen(self, audio: bool = False, region: bool = False) -> str:
        """Trigger Caelestia screen recording.

        :param audio: Include audio stream flag.
        :param region: Select region flag.
        """
        return caelestia_ipc.record(audio=audio, region=region)

    @strand(description="Call raw Caelestia Quickshell IPC target and method.", tier="mutate")
    def caelestia_call_ipc(self, target: str, method: str, args: list[str] | None = None) -> str:
        """Call raw Caelestia Quickshell IPC target and method.

        :param target: Target IPC module (e.g. 'drawers', 'notifs', 'lock').
        :param method: IPC method name (e.g. 'toggle', 'clear', 'lock').
        :param args: Method arguments list.
        """
        arg_list = args or []
        if isinstance(arg_list, str):
            arg_list = [arg_list]
        return caelestia_ipc.call_ipc(target, method, *arg_list)
