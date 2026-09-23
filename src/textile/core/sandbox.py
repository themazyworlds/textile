"""
Textile Linux Landlock Kernel Sandbox.

Provides unprivileged, kernel-enforced read-only confinement for OBSERVE and INTERACT strands.
When applied, the Linux kernel blocks all filesystem writes, unlinks, and truncates (EPERM),
even if code attempts `import os; os.remove(...)`.
"""

import ctypes
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# Syscall numbers on x86_64
SYS_landlock_create_ruleset = 444
SYS_landlock_add_rule = 445
SYS_landlock_restrict_self = 446
PR_SET_NO_NEW_PRIVS = 38

# Landlock access flags
LANDLOCK_ACCESS_FS_EXECUTE = 1 << 0
LANDLOCK_ACCESS_FS_WRITE_FILE = 1 << 1
LANDLOCK_ACCESS_FS_READ_FILE = 1 << 2
LANDLOCK_ACCESS_FS_READ_DIR = 1 << 3
LANDLOCK_ACCESS_FS_REMOVE_DIR = 1 << 4
LANDLOCK_ACCESS_FS_REMOVE_FILE = 1 << 5
LANDLOCK_ACCESS_FS_MAKE_CHAR = 1 << 6
LANDLOCK_ACCESS_FS_MAKE_DIR = 1 << 7
LANDLOCK_ACCESS_FS_MAKE_REG = 1 << 8
LANDLOCK_ACCESS_FS_MAKE_SOCK = 1 << 9
LANDLOCK_ACCESS_FS_MAKE_FIFO = 1 << 10
LANDLOCK_ACCESS_FS_MAKE_BLOCK = 1 << 11
LANDLOCK_ACCESS_FS_MAKE_SYM = 1 << 12
LANDLOCK_ACCESS_FS_REFER = 1 << 13
LANDLOCK_ACCESS_FS_TRUNCATE = 1 << 14

ACCESS_FS_RO = LANDLOCK_ACCESS_FS_EXECUTE | LANDLOCK_ACCESS_FS_READ_FILE | LANDLOCK_ACCESS_FS_READ_DIR
ACCESS_FS_WR = (
    LANDLOCK_ACCESS_FS_WRITE_FILE
    | LANDLOCK_ACCESS_FS_REMOVE_DIR
    | LANDLOCK_ACCESS_FS_REMOVE_FILE
    | LANDLOCK_ACCESS_FS_MAKE_DIR
    | LANDLOCK_ACCESS_FS_MAKE_REG
    | LANDLOCK_ACCESS_FS_TRUNCATE
)
ALL_HANDLED_ACCESS = ACCESS_FS_RO | ACCESS_FS_WR


class LandlockRulesetAttr(ctypes.Structure):
    _fields_ = [("handled_access_fs", ctypes.c_uint64)]


class LandlockPathBeneathAttr(ctypes.Structure):
    _fields_ = [
        ("allowed_access", ctypes.c_uint64),
        ("parent_fd", ctypes.c_int32),
    ]


ENOSYS_ERRNO = 38


class LandlockSandbox:
    """Linux Landlock filesystem confinement manager."""

    @classmethod
    def is_supported(cls) -> bool:
        if sys.platform != "linux":
            return False
        try:
            libc = ctypes.CDLL(None, use_errno=True)
            res = libc.syscall(SYS_landlock_create_ruleset, 0, 0, 1)
            return res >= 0 or ctypes.get_errno() != ENOSYS_ERRNO
        except (OSError, AttributeError):
            return False

    @classmethod
    def apply_read_only(cls, allowed_read_path: str = "/") -> bool:
        """
        Confine the current process to read-only filesystem access.
        All mutating operations (write, unlink, rmdir, truncate) will be blocked
        directly by the Linux kernel with EPERM.
        """
        if not cls.is_supported():
            logger.debug("Landlock is not supported on this platform/kernel.")
            return False

        try:
            libc = ctypes.CDLL(None, use_errno=True)

            attr = LandlockRulesetAttr()
            attr.handled_access_fs = ALL_HANDLED_ACCESS
            ruleset_fd = libc.syscall(
                SYS_landlock_create_ruleset, ctypes.byref(attr), ctypes.sizeof(attr), 0
            )
            if ruleset_fd < 0:
                logger.debug("Failed creating Landlock ruleset: errno %s", ctypes.get_errno())
                return False

            root_fd = os.open(allowed_read_path, os.O_PATH | os.O_CLOEXEC)
            try:
                path_attr = LandlockPathBeneathAttr()
                path_attr.allowed_access = ACCESS_FS_RO
                path_attr.parent_fd = root_fd

                ret_add = libc.syscall(SYS_landlock_add_rule, ruleset_fd, 1, ctypes.byref(path_attr), 0)
                if ret_add < 0:
                    logger.debug("Failed adding Landlock rule: errno %s", ctypes.get_errno())
                    os.close(ruleset_fd)
                    return False
            finally:
                os.close(root_fd)

            # Prevent future privilege elevation
            libc.prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0)

            # Enforce confinement on this process
            ret_restrict = libc.syscall(SYS_landlock_restrict_self, ruleset_fd, 0)
            os.close(ruleset_fd)

            return ret_restrict == 0
        except (OSError, AttributeError, RuntimeError) as e:
            logger.debug("Error applying Landlock sandbox: %s", e)
            return False


class BubblewrapSandbox:
    """
    Linux Bubblewrap (bwrap) unprivileged container isolation manager.
    Enforces namespace isolation (mount, PID, IPC, network) and workspace confinement.
    Zero hardcoded file blacklists; mounts /home as an empty tmpfs and binds
    strictly the target workspace.
    """

    @classmethod
    def is_available(cls) -> bool:
        """Check if bubblewrap (bwrap) executable is present and working."""
        if sys.platform != "linux":
            return False
        bwrap_path = shutil.which("bwrap")
        if not bwrap_path:
            return False
        try:
            res = subprocess.run(
                [bwrap_path, "--version"],
                capture_output=True,
                text=True,
                timeout=2.0,
                check=False,
            )
            return res.returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False

    @classmethod
    def wrap_command(
        cls,
        cmd: list[str],
        tier: str,
        workspace_root: str | Path | None = None,
        allow_network: bool = False,
    ) -> list[str]:
        """
        Wrap command in a bwrap sandbox container tailored to the capability tier.

        - OBSERVE / INTERACT: Read-only workspace (--ro-bind), isolated network, empty /home.
        - MUTATE: Read-write workspace (--bind), isolated network, empty /home.
        - PRIVILEGED: Host execution (no bwrap wrapping, controlled via caller seat).
        """
        bwrap_path = shutil.which("bwrap")
        if not bwrap_path:
            return cmd

        tier_upper = str(tier).upper()
        if "PRIVILEGED" in tier_upper:
            # Privileged tier operations interact directly with system / seat
            return cmd

        is_writable = "MUTATE" in tier_upper

        ws = Path(workspace_root or os.getcwd()).resolve()

        bwrap_args = [
            bwrap_path,
            "--ro-bind", "/usr", "/usr",
            "--symlink", "usr/lib", "/lib",
            "--symlink", "usr/lib", "/lib64",
            "--symlink", "usr/bin", "/bin",
            "--ro-bind-try", "/etc", "/etc",
            "--dev", "/dev",
            "--proc", "/proc",
            "--tmpfs", "/tmp",  # noqa: S108 - In-memory container tmpfs
            "--tmpfs", "/home",
        ]

        if not allow_network:
            bwrap_args.append("--unshare-all")
        else:
            bwrap_args.extend(["--unshare-user", "--unshare-pid", "--unshare-ipc", "--unshare-uts"])

        # Bind workspace
        bind_flag = "--bind" if is_writable else "--ro-bind"
        bwrap_args.extend([bind_flag, str(ws), str(ws)])
        bwrap_args.extend(["--chdir", str(ws)])
        bwrap_args.extend(["--setenv", "PATH", os.environ.get("PATH", "/usr/bin:/bin")])
        bwrap_args.extend(["--setenv", "UV_CACHE_DIR", "/tmp/uv_cache"])  # noqa: S108 - Sandboxed container cache

        # Pass python path if present
        python_path = os.environ.get("PYTHONPATH")
        if python_path:
            bwrap_args.extend(["--setenv", "PYTHONPATH", python_path])

        bwrap_args.extend(cmd)
        return bwrap_args

