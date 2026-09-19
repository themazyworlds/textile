"""
Developer Shell Command Execution & Timers Capability Yarn.
Provides bash command execution and background job spawning.
Layer 10 (Core POSIX).
"""

import os
import subprocess

from textile.core.base import LAYER_BASE, CapabilityTier, Yarn, strand


class DevShell(Yarn):
    name = "dev_shell"
    description = "Non-interactive POSIX shell execution."
    version = "1.2.0"
    layer = LAYER_BASE  # Layer 10

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
                proc = subprocess.Popen(cmd, shell=True, start_new_session=True, cwd=os.getcwd())
                try:
                    from textile.yarns.system_core.process import ProcessControl

                    ProcessControl.register_bg_job(proc.pid, cmd, "shell_cmd")
                except Exception:
                    pass
                return f"[Started in background (PID {proc.pid})]: {cmd}"
            except Exception as e:
                return f"Error starting background command: {e!s}"

        try:
            res = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=25,
                cwd=os.getcwd()
            )
            out = res.stdout
            if res.stderr:
                out += f"\n[stderr]: {res.stderr}"
            if not out.strip():
                out = f"[Command exited with code {res.returncode}]"
            return out.strip()[:2500]
        except subprocess.TimeoutExpired:
            return f"Error: Command '{cmd[:40]}' timed out after 25 seconds."
        except Exception as e:
            return f"Error executing command: {e!s}"
