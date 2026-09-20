"""
Developer Shell Command Execution & Timers Capability Yarn.
Provides bash command execution and background job spawning.
Layer 10 (Core POSIX).
"""

import contextlib
import os
import subprocess

from textile.core.base import CapabilityTier, Yarn, strand
from textile.yarns.system_core.process import ProcessControl


class DevShell(Yarn):

    def is_available(self) -> bool:
        return True

    @strand(
        description="Execute a bash shell command for developer tasks (git, tests, builds, package managers).",
        tier=CapabilityTier.SYSTEM_EXEC,
    )
    def run_command(self, command: str, background: bool = False) -> str:
        """Execute a bash shell command for developer tasks (git, tests, builds, package managers).

        :param command: The exact shell command line string to run.
        :param background: Set to true to launch process in background without blocking.
        """
        cmd = command.strip()
        if not cmd:
            return "Error: No command provided."

        if background:
            try:
                proc = subprocess.Popen(cmd, shell=True, start_new_session=True, cwd=os.getcwd())  # noqa: S602
                with contextlib.suppress(AttributeError, KeyError, TypeError, ValueError):
                    ProcessControl.register_bg_job(proc.pid, cmd, "shell_cmd")
                return f"[Started in background (PID {proc.pid})]: {cmd}"
            except (OSError, subprocess.SubprocessError) as e:
                return f"Error starting background command: {e!s}"

        try:
            res = subprocess.run(  # noqa: S602
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=25,
                cwd=os.getcwd(),
                check=False,
            )
            out = res.stdout
            if res.stderr:
                out += f"\n[stderr]: {res.stderr}"
            if not out.strip():
                out = f"[Command exited with code {res.returncode}]"
            return out.strip()[:2500]
        except subprocess.TimeoutExpired:
            return f"Error: Command '{cmd[:40]}' timed out after 25 seconds."
        except (OSError, subprocess.SubprocessError) as e:
            return f"Error executing command: {e!s}"
