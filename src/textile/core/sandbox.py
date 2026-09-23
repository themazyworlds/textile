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
from collections.abc import Callable
from pathlib import Path

logger = logging.getLogger(__name__)


def _resolve_dbus_session_bind() -> list[str]:
    """Resolve dynamic D-Bus session bus socket file mount without mounting entire /run."""
    addr = os.environ.get("DBUS_SESSION_BUS_ADDRESS", "")
    if addr.startswith("unix:path="):
        sock_path = addr.split("unix:path=")[1].split(",")[0]
        if os.path.exists(sock_path):
            return ["--ro-bind", sock_path, sock_path, "--setenv", "DBUS_SESSION_BUS_ADDRESS", addr]
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    if runtime:
        default_sock = os.path.join(runtime, "bus")
        if os.path.exists(default_sock):
            fallback_addr = f"unix:path={default_sock}"
            return ["--ro-bind", default_sock, default_sock, "--setenv", "DBUS_SESSION_BUS_ADDRESS", fallback_addr]
    return []


def _resolve_dbus_system_bind() -> list[str]:
    """Resolve dynamic D-Bus system bus socket file mount."""
    for sock_path in ["/run/dbus/system_bus_socket", "/var/run/dbus/system_bus_socket"]:
        if os.path.exists(sock_path):
            return ["--ro-bind", sock_path, sock_path]
    return []


def _resolve_display_bind() -> list[str]:
    """Resolve dynamic Wayland / X11 display socket mounts."""
    args = []
    wayland_display = os.environ.get("WAYLAND_DISPLAY")
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    if wayland_display and runtime:
        wl_sock = os.path.join(runtime, wayland_display)
        if os.path.exists(wl_sock):
            args.extend([
                "--ro-bind", wl_sock, wl_sock,
                "--setenv", "WAYLAND_DISPLAY", wayland_display,
                "--setenv", "XDG_RUNTIME_DIR", runtime,
            ])
    x11_display = os.environ.get("DISPLAY")
    if x11_display:
        args.extend(["--setenv", "DISPLAY", x11_display])
        x11_sock = os.path.join("/", "tmp", ".X11-unix")
        if os.path.exists(x11_sock):
            args.extend(["--ro-bind", x11_sock, x11_sock])
    return args


def _resolve_sound_bind() -> list[str]:
    """Resolve dynamic PipeWire / PulseAudio sound socket mounts."""
    args = []
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    if runtime:
        pw_sock = os.path.join(runtime, "pipewire-0")
        if os.path.exists(pw_sock):
            args.extend(["--ro-bind", pw_sock, pw_sock])
        pulse_dir = os.path.join(runtime, "pulse")
        if os.path.exists(pulse_dir):
            args.extend(["--ro-bind", pulse_dir, pulse_dir])
    return args


KNOWN_RESOURCES: dict[str, Callable[[], list[str]]] = {
    "dbus-session": _resolve_dbus_session_bind,
    "dbus-system": _resolve_dbus_system_bind,
    "display": _resolve_display_bind,
    "sound": _resolve_sound_bind,
}

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
        resources: list[str] | None = None,
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
        container_tmp = os.path.join("/", "tmp")
        container_home = os.path.join("/", "home")
        uv_cache = os.path.join(container_tmp, "uv_cache")

        bwrap_args = [
            bwrap_path,
            "--ro-bind", "/usr", "/usr",
            "--symlink", "usr/lib", "/lib",
            "--symlink", "usr/lib", "/lib64",
            "--symlink", "usr/bin", "/bin",
            "--symlink", "usr/bin", "/sbin",
            "--ro-bind-try", "/etc", "/etc",
            "--dev", "/dev",
            "--proc", "/proc",
            "--tmpfs", container_tmp,
            "--tmpfs", container_home,
        ]

        # Securely resolve declared resources from KNOWN_RESOURCES catalog (Flatpak/Snap model)
        if resources:
            for res_name in resources:
                clean_res = str(res_name).strip().lower()
                if clean_res in KNOWN_RESOURCES:
                    bwrap_args.extend(KNOWN_RESOURCES[clean_res]())
                else:
                    logger.warning(f"Unrecognized sandbox resource request '{res_name}' ignored.")

        if not allow_network:
            bwrap_args.append("--unshare-all")
        else:
            bwrap_args.extend(["--unshare-user", "--unshare-pid", "--unshare-ipc", "--unshare-uts"])

        # Bind workspace
        bind_flag = "--bind" if is_writable else "--ro-bind"
        bwrap_args.extend([bind_flag, str(ws), str(ws)])
        bwrap_args.extend(["--chdir", str(ws)])
        bwrap_args.extend(["--setenv", "PATH", os.environ.get("PATH", "/usr/bin:/bin")])
        bwrap_args.extend(["--setenv", "UV_CACHE_DIR", uv_cache])

        # Pass python path if present
        python_path = os.environ.get("PYTHONPATH")
        if python_path:
            bwrap_args.extend(["--setenv", "PYTHONPATH", python_path])

        bwrap_args.extend(cmd)
        return bwrap_args

