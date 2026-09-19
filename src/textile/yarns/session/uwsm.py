"""
UWSM (Universal Wayland Session Manager) Capability Yarn for Textile.
Exposes app launching and unit management via systemd user units under UWSM scope.
Layer 150 (Session Manager).
"""

import os
import shlex
import shutil
import subprocess
from typing import Any, Dict, List, Optional
from textile.core.base import BaseYarn, strand, LAYER_SESSION_MANAGER, resolve_terminal_and_shell


class UWSM(BaseYarn):
    name = "uwsm"
    description = "UWSM Systemd Desktop Application Launcher & Scope Management."
    version = "1.0.0"
    layer = LAYER_SESSION_MANAGER  # Layer 150
    dependencies = [{"type": "system_binary", "target": "uwsm"}]

    def is_available(self) -> bool:
        return shutil.which("uwsm") is not None

    def _run_uwsm(self, action: str, target: str = "") -> str:
        cmd = ["uwsm", action]
        if target:
            cmd.append(target)
        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=5)
            return res.stdout
        except Exception as e:
            return f"Error running UWSM action: {e}"

    @strand(description="Launch a desktop application inside a dedicated systemd user scope via UWSM for clean cgroup tracking.", capability="desktop.app_launcher")
    def launch_app(self, command: str, is_tui: bool = False, args: Optional[List[str]] = None) -> str:
        """Launch a desktop application inside a dedicated systemd user scope via UWSM for clean cgroup tracking.

        :param command: The command or binary name to launch (e.g. 'firefox', 'foot', 'nvim').
        :param is_tui: Terminal/TUI application flag. Set to true to launch inside a terminal emulator window.
        :param args: Optional list of arguments for the application.
        """
        cmd = str(command or "").strip()
        cmd_args = args or []
        if isinstance(cmd_args, str):
            cmd_args = [cmd_args]

        if not cmd:
            return "Error: No command specified to launch."

        if is_tui:
            term, shell = resolve_terminal_and_shell()
            full_cmd = ["uwsm", "app", "--", term, "-e", shell, "-i", "-c", cmd] + [str(a) for a in cmd_args]
        else:
            full_cmd = ["uwsm", "app", "--", cmd] + [str(a) for a in cmd_args]

        try:
            proc = subprocess.Popen(
                full_cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True
            )
            mode_str = " (TUI terminal scope)" if is_tui else ""
            return f"Successfully launched '{cmd}' via UWSM cgroup scope{mode_str} (PID {proc.pid})."
        except Exception as e:
            return f"Error launching app via UWSM: {e}"

    @strand(description="Check UWSM session status and systemd user unit hierarchy.")
    def uwsm_status(self, unit: Optional[str] = None) -> str:
        """Check UWSM session status and systemd user unit hierarchy.

        :param unit: Optional systemd unit name to query status.
        """
        return self._run_uwsm("status", unit or "")

    @strand(description="Check UWSM environment compatibility and systemd support.")
    def uwsm_check(self, target: Optional[str] = None) -> str:
        """Check UWSM environment compatibility and systemd support.

        :param target: Optional environment or capability target.
        """
        return self._run_uwsm("check", target or "")

    @strand(description="Stop a UWSM systemd user unit or active session.")
    def uwsm_stop(self, unit: Optional[str] = None) -> str:
        """Stop a UWSM systemd user unit or active session.

        :param unit: Systemd unit name or scope to stop.
        """
        return self._run_uwsm("stop", unit or "")

    @strand(description="Finalize UWSM environment variables and session cleanup.")
    def uwsm_finalize(self, target: Optional[str] = None) -> str:
        """Finalize UWSM environment variables and session cleanup.

        :param target: Optional target for finalize.
        """
        return self._run_uwsm("finalize", target or "")
