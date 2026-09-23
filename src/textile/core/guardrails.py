"""
Textile Core Capability Guardrails & Ambient Security Boundaries.

Provides zero-blacklist, mathematically bounded sandboxes:
1. ScopedPath / Root Anchor Jail: Guaranteed confinement via Path.is_relative_to().
2. SessionProcessGuard: POSIX session tree confinement via getsid().
3. SafeExec: Direct argument vector execution bypassing /bin/sh.
"""

import os
import shlex
import subprocess
from pathlib import Path


class AccessBoundaryError(PermissionError):
    """Raised when an operation attempts to escape its ambient capability boundary."""
    pass


class ScopedPath:
    """
    Mathematical root anchor jail.
    Guarantees all file operations remain inside the declared root boundary.
    Zero hardcoded forbidden path lists.
    """

    def __init__(self, root: str | Path | None = None):
        if root is not None:
            self._root = Path(root).expanduser().resolve()
        else:
            # Default to active working directory or user home
            self._root = Path.cwd().resolve()

    @property
    def root(self) -> Path:
        return self._root

    def resolve(self, relative_or_subpath: str | Path) -> Path:
        """
        Safely resolve a target path relative to the root anchor.
        Mathematically verifies that target.is_relative_to(root) is True.
        """
        raw = str(relative_or_subpath).strip()
        if not raw or raw == ".":
            return self._root

        target = (self._root / Path(os.path.expanduser(raw))).resolve()

        if not target.is_relative_to(self._root):
            raise AccessBoundaryError(
                f"Access Denied: Path '{raw}' escapes declared capability root '{self._root}'."
            )

        return target


class SessionProcessGuard:
    """
    POSIX session tree process guard.
    Guarantees operations can only target processes belonging to the active desktop session tree.
    Zero hardcoded PID blacklists.
    """

    @staticmethod
    def get_active_session_id() -> int:
        return os.getsid(0)

    @classmethod
    def verify_pid_in_session(cls, pid: int) -> int:
        """
        Verify that target PID belongs strictly to the caller's desktop session tree.
        Raises AccessBoundaryError if target is in another session or system daemon scope.
        """
        target_pid = int(pid)
        if target_pid <= 0:
            raise AccessBoundaryError(f"Access Denied: Invalid target PID {target_pid}.")

        try:
            current_sid = cls.get_active_session_id()
            target_sid = os.getsid(target_pid)
        except (ProcessLookupError, OSError) as e:
            raise AccessBoundaryError(f"Process verification failed for PID {target_pid}: {e}") from e

        if current_sid != target_sid:
            raise AccessBoundaryError(
                f"Access Denied: PID {target_pid} (session {target_sid}) is outside active session {current_sid}."
            )

        return target_pid


class SafeExec:
    """
    Direct argument vector subprocess invoker.
    Strictly disallows shell=True to prevent subshell command injections.
    """

    @staticmethod
    def run_vector(
        cmd: list[str] | str,
        timeout: float = 15.0,
        env: dict[str, str] | None = None,
        cwd: str | Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        argv = shlex.split(cmd) if isinstance(cmd, str) else [str(x) for x in cmd]

        if not argv:
            raise ValueError("No command specified.")

        return subprocess.run(
            argv,
            shell=False,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env=env,
            cwd=cwd,
        )
