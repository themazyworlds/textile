"""
Native Process Management & Background Job Tracking Capability Yarn.
Provides POSIX signals, process inspection, system load monitoring, and background job registry.
Layer 10 (Core POSIX).
"""

import contextlib
import os
import shlex
import signal as sig_mod
import subprocess
import time
from typing import Any

from textile.core.base import Yarn, strand
from textile.core.guardrails import AccessBoundaryError, SessionProcessGuard

BACKGROUND_JOBS: dict[int, dict[str, Any]] = {}
MAX_PROC_SCAN_LIMIT = 50


class ProcessControl(Yarn):
    def is_available(self) -> bool:
        return True

    @staticmethod
    def register_bg_job(pid: int, command: str, job_type: str = "app"):
        BACKGROUND_JOBS[pid] = {
            "pid": pid,
            "command": command,
            "type": job_type,
            "start_time": time.time(),
            "status": "running",
        }

    @strand(
        description="Launch a desktop application or background command (routed through UWSM scope if active).",
        capability="desktop.app_launcher",
        tier="interact",
    )
    def launch_app(self, app: str, is_tui: bool = False) -> str:
        """Launch a desktop application or background command.

        :param app: Application command or binary to launch.
        :param is_tui: Whether to launch in a terminal.
        """
        app_clean = app.strip()
        if not app_clean:
            return "Error: No application command provided."
        try:
            argv = shlex.split(app_clean)
            proc = subprocess.Popen(argv, shell=False, start_new_session=True, cwd=os.getcwd())
            self.register_bg_job(proc.pid, app_clean, "app")
            return f"Universal Launcher: Started '{app_clean}' in background (PID {proc.pid})."
        except (OSError, ValueError, subprocess.SubprocessError) as e:
            return f"Error launching application: {e}"

    @strand(
        description="List running system processes with PID, CPU/memory usage, user, and command line.",
        tier="observe",
    )
    def process_list(self, filter: str | None = None) -> list[dict[str, Any]]:
        """List running system processes with PID, CPU/memory usage, user, and command line.

        :param filter: Optional filter string for process name or command.
        """
        filter_name = str(filter or "").strip().lower()
        procs = []
        try:
            for entry in os.scandir("/proc"):
                if entry.is_dir() and entry.name.isdigit():
                    p = int(entry.name)
                    comm_path = os.path.join(entry.path, "comm")
                    if os.path.exists(comm_path):
                        with contextlib.suppress(OSError, ValueError, TypeError):
                            with open(comm_path, encoding="utf-8", errors="replace") as f:
                                pname = f.read().strip()
                            if filter_name and filter_name not in pname.lower():
                                continue
                            procs.append({"pid": p, "name": pname})
                            if len(procs) >= MAX_PROC_SCAN_LIMIT:
                                break
            return procs
        except (OSError, ValueError, TypeError) as e:
            return [{"error": f"Error scanning /proc: {e}"}]

    @strand(description="Send a POSIX signal to terminate or signal a process by PID.", tier="mutate")
    def process_kill(self, pid: int, signal: str = "SIGTERM") -> str:
        """Send a POSIX signal to terminate or signal a process by PID.

        :param pid: Process ID to signal.
        :param signal: Signal name (e.g. SIGTERM, SIGKILL, SIGHUP, SIGINT).
        """
        sig_name = str(signal or "SIGTERM").strip().upper()
        try:
            target_pid = SessionProcessGuard.verify_pid_in_session(int(pid))
            sig_num = getattr(sig_mod, sig_name, sig_mod.SIGTERM)
            os.kill(target_pid, sig_num)
            BACKGROUND_JOBS.pop(target_pid, None)
            return f"Successfully sent signal {sig_name} ({sig_num}) to PID {target_pid}."
        except AccessBoundaryError as e:
            return f"Error: {e}"
        except ProcessLookupError:
            BACKGROUND_JOBS.pop(int(pid), None)
            return f"Process PID {pid} not found (already exited)."
        except PermissionError:
            return f"Error: Permission denied sending signal to PID {pid}."
        except (OSError, ValueError, TypeError) as e:
            return f"Error sending signal: {e}"

    @strand(description="List background jobs spawned and tracked by Textile.", tier="observe")
    def process_list_bg_jobs(self) -> dict[str, Any]:
        """List background jobs spawned and tracked by Textile."""
        now = time.time()
        active_jobs = []
        stale_pids = []
        for p, job in list(BACKGROUND_JOBS.items()):
            try:
                os.kill(p, 0)
                job_info = dict(job)
                job_info["elapsed_seconds"] = round(now - job["start_time"], 1)
                active_jobs.append(job_info)
            except (ProcessLookupError, PermissionError):
                stale_pids.append(p)
        for p in stale_pids:
            BACKGROUND_JOBS.pop(p, None)
        return {"active_bg_jobs_count": len(active_jobs), "jobs": active_jobs}

    @strand(description="Get CPU 1, 5, and 15-minute load averages and CPU core counts.", tier="observe")
    def process_get_loadavg(self) -> dict[str, Any]:
        """Get CPU 1, 5, and 15-minute load averages and CPU core counts."""
        try:
            if hasattr(os, "getloadavg"):
                l1, l5, l15 = os.getloadavg()
                return {
                    "1_min_load": round(l1, 2),
                    "5_min_load": round(l5, 2),
                    "15_min_load": round(l15, 2),
                    "cpu_cores": os.cpu_count() or 1,
                }
            return {"cpu_cores": os.cpu_count() or 1, "notice": "Load average metric not supported platform."}
        except (OSError, AttributeError) as e:
            return {"error": f"Error reading load average: {e}"}

    @strand(description="Get nice priority level of a running process by PID.", tier="observe")
    def process_get_priority(self, pid: int) -> str:
        """Get nice priority level of a running process by PID.

        :param pid: Target Process ID (PID).
        """
        if not hasattr(os, "getpriority"):
            return "Error: Priority management not supported."
        try:
            return f"PID {pid} nice priority: {os.getpriority(os.PRIO_PROCESS, int(pid))}"
        except (OSError, ValueError, TypeError) as e:
            return f"Error getting priority: {e}"

    @strand(description="Set nice priority level (-20 to 19) of a process by PID.", tier="mutate")
    def process_set_priority(self, pid: int, priority: int = 0) -> str:
        """Set nice priority level (-20 to 19) of a process by PID.

        :param pid: Target Process ID (PID).
        :param priority: Nice priority level (-20 highest priority to 19 lowest priority).
        """
        if not hasattr(os, "setpriority"):
            return "Error: Priority management not supported."
        try:
            target_pid = SessionProcessGuard.verify_pid_in_session(int(pid))
            os.setpriority(os.PRIO_PROCESS, target_pid, int(priority))
            return f"PID {target_pid} nice priority set to {priority}."
        except AccessBoundaryError as e:
            return f"Error: {e}"
        except (OSError, ValueError, TypeError) as e:
            return f"Error setting priority: {e}"
