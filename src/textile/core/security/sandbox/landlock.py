"""
Linux Landlock filesystem confinement manager.
Enforces ABI v1-v3 read-only kernel walls via unprivileged syscalls.
"""

import ctypes
import os
import sys

from textile.core.telemetry.log import get_logger

logger = get_logger(__name__)

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
LANDLOCK_ACCESS_FS_MAKE_DIR = 1 << 7
LANDLOCK_ACCESS_FS_MAKE_REG = 1 << 8
LANDLOCK_ACCESS_FS_TRUNCATE = 1 << 14

ACCESS_FS_RO = LANDLOCK_ACCESS_FS_EXECUTE | LANDLOCK_ACCESS_FS_READ_FILE | LANDLOCK_ACCESS_FS_READ_DIR
ALL_HANDLED_ACCESS = ACCESS_FS_RO | (
    LANDLOCK_ACCESS_FS_WRITE_FILE
    | LANDLOCK_ACCESS_FS_REMOVE_DIR
    | LANDLOCK_ACCESS_FS_REMOVE_FILE
    | LANDLOCK_ACCESS_FS_MAKE_DIR
    | LANDLOCK_ACCESS_FS_MAKE_REG
    | LANDLOCK_ACCESS_FS_TRUNCATE
)

ENOSYS_ERRNO = 38


class LandlockRulesetAttr(ctypes.Structure):
    _fields_ = [("handled_access_fs", ctypes.c_uint64)]


class LandlockPathBeneathAttr(ctypes.Structure):
    _fields_ = [
        ("allowed_access", ctypes.c_uint64),
        ("parent_fd", ctypes.c_int32),
    ]


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
        """Confine the current process to read-only filesystem access."""
        if not cls.is_supported():
            logger.debug("sandbox.landlock_unsupported")
            return False

        try:
            libc = ctypes.CDLL(None, use_errno=True)
            attr = LandlockRulesetAttr()
            attr.handled_access_fs = ALL_HANDLED_ACCESS
            ruleset_fd = libc.syscall(SYS_landlock_create_ruleset, ctypes.byref(attr), ctypes.sizeof(attr), 0)
            if ruleset_fd < 0:
                # Fallback handled access without TRUNCATE for Linux kernels < 6.2 (Landlock ABI v1/v2)
                attr.handled_access_fs = ALL_HANDLED_ACCESS & ~LANDLOCK_ACCESS_FS_TRUNCATE
                ruleset_fd = libc.syscall(SYS_landlock_create_ruleset, ctypes.byref(attr), ctypes.sizeof(attr), 0)
                if ruleset_fd < 0:
                    return False

            root_fd = os.open(allowed_read_path, os.O_PATH | os.O_CLOEXEC)
            try:
                path_attr = LandlockPathBeneathAttr()
                path_attr.allowed_access = ACCESS_FS_RO
                path_attr.parent_fd = root_fd

                ret_add = libc.syscall(SYS_landlock_add_rule, ruleset_fd, 1, ctypes.byref(path_attr), 0)
                if ret_add < 0:
                    os.close(ruleset_fd)
                    return False
            finally:
                os.close(root_fd)

            libc.prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0)
            ret_restrict = libc.syscall(SYS_landlock_restrict_self, ruleset_fd, 0)
            os.close(ruleset_fd)
            return ret_restrict == 0
        except (OSError, AttributeError, RuntimeError) as e:
            logger.debug("sandbox.landlock_apply_failed", error=str(e))
            return False
