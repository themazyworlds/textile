"""
UWSM (Universal Wayland Session Manager) Capability Yarn for Textile.
Exposes app launching and unit management via systemd user units under UWSM scope.
Layer 150 (Session Manager).
"""

import shutil
import subprocess

from textile.core.base import (
    Yarn,
    resolve_terminal_and_shell,
    strand,
)


class UWSM(Yarn):
    def is_available(self) -> bool:
        return shutil.which("uwsm") is not None

    def _run_uwsm(self, action: str, target: str = "") -> str:
        cmd = ["uwsm", action]
        if target:
            cmd.append(target)
        try:
            res = subprocess.run(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=5, check=False
            )
            return res.stdout
        except (OSError, subprocess.SubprocessError) as e:
            return f"Error running UWSM action: {e}"

    @strand(capability="desktop.app_launcher", tier="interact")
    def launch_app(self, command: str, is_tui: bool = False, args: list[str] | None = None) -> str:
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
                full_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True
            )
            mode_str = " (TUI terminal scope)" if is_tui else ""
            return f"Successfully launched '{cmd}' via UWSM cgroup scope{mode_str} (PID {proc.pid})."
        except (OSError, subprocess.SubprocessError) as e:
            return f"Error launching app via UWSM: {e}"

    @strand(tier="observe")
    def uwsm_status(self, unit: str | None = None) -> str:
        """Check UWSM session status and systemd user unit hierarchy.

        :param unit: Optional systemd unit name to query status.
        """
        return self._run_uwsm("status", unit or "")

    @strand(tier="observe")
    def uwsm_check(self, target: str | None = None) -> str:
        """Check UWSM environment compatibility and systemd support.

        :param target: Optional environment or capability target.
        """
        return self._run_uwsm("check", target or "")

    @strand(tier="privileged")
    def uwsm_stop(self, unit: str | None = None) -> str:
        """Stop a UWSM systemd user unit or active session.

        :param unit: Systemd unit name or scope to stop.
        """
        return self._run_uwsm("stop", unit or "")

    @strand(tier="privileged")
    def uwsm_finalize(self, target: str | None = None) -> str:
        """Finalize UWSM environment variables and session cleanup.

        :param target: Optional target for finalize.
        """
        return self._run_uwsm("finalize", target or "")
