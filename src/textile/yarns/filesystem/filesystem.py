"""
File System & Linux inotify Operations Capability Yarn.
Provides file operations, atomic writes, and Linux kernel inotify real-time event monitoring.
Layer 10 (Core POSIX).
"""

import contextlib
import ctypes
import ctypes.util
import fnmatch
import logging
import os
import select
import shutil
import stat
import struct
import tempfile
import time
from pathlib import Path
from typing import Any, Literal

from textile.core.base import CapabilityTier, Yarn, strand
from textile.core.guardrails import ScopedPath

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Linux inotify Constants
# ---------------------------------------------------------------------------
IN_ACCESS = 0x00000001
IN_MODIFY = 0x00000002
IN_ATTRIB = 0x00000004
IN_CLOSE_WRITE = 0x00000008
IN_CLOSE_NOWRITE = 0x00000010
IN_OPEN = 0x00000020
IN_MOVED_FROM = 0x00000040
IN_MOVED_TO = 0x00000080
IN_CREATE = 0x00000100
IN_DELETE = 0x00000200
IN_DELETE_SELF = 0x00000400
IN_MOVE_SELF = 0x00000800
IN_UNMOUNT = 0x00002000
IN_Q_OVERFLOW = 0x00004000
IN_IGNORED = 0x00008000
IN_ONLYDIR = 0x01000000
IN_DONT_FOLLOW = 0x02000000
IN_EXCL_UNLINK = 0x04000000
IN_MASK_CREATE = 0x10000000
IN_MASK_ADD = 0x20000000
IN_ISDIR = 0x40000000
IN_ONESHOT = 0x80000000

IN_CLOSE = (IN_CLOSE_WRITE | IN_CLOSE_NOWRITE)
IN_MOVE = (IN_MOVED_FROM | IN_MOVED_TO)
IN_ALL_EVENTS = (
    IN_ACCESS | IN_MODIFY | IN_ATTRIB | IN_CLOSE_WRITE | IN_CLOSE_NOWRITE
    | IN_OPEN | IN_MOVED_FROM | IN_MOVED_TO | IN_CREATE | IN_DELETE
    | IN_DELETE_SELF | IN_MOVE_SELF
)

IN_CLOEXEC = 0o2000000
IN_NONBLOCK = 0o4000

EVENT_NAME_MAP = {
    IN_ACCESS: "IN_ACCESS",
    IN_MODIFY: "IN_MODIFY",
    IN_ATTRIB: "IN_ATTRIB",
    IN_CLOSE_WRITE: "IN_CLOSE_WRITE",
    IN_CLOSE_NOWRITE: "IN_CLOSE_NOWRITE",
    IN_OPEN: "IN_OPEN",
    IN_MOVED_FROM: "IN_MOVED_FROM",
    IN_MOVED_TO: "IN_MOVED_TO",
    IN_CREATE: "IN_CREATE",
    IN_DELETE: "IN_DELETE",
    IN_DELETE_SELF: "IN_DELETE_SELF",
    IN_MOVE_SELF: "IN_MOVE_SELF",
    IN_UNMOUNT: "IN_UNMOUNT",
    IN_Q_OVERFLOW: "IN_Q_OVERFLOW",
    IN_IGNORED: "IN_IGNORED",
    IN_ISDIR: "IN_ISDIR",
}

ALIAS_TO_MASK = {
    "all": IN_ALL_EVENTS,
    "modify": IN_MODIFY | IN_ATTRIB,
    "create": IN_CREATE | IN_MOVED_TO,
    "delete": IN_DELETE | IN_MOVED_FROM | IN_DELETE_SELF,
    "write": IN_CLOSE_WRITE | IN_MODIFY,
    "move": IN_MOVE,
    "close": IN_CLOSE,
}


class InotifyAPI:
    """Linux kernel inotify C-types wrapper API."""

    def __init__(self) -> None:
        self._libc: Any = None
        self._fd: int | None = None
        self._watches: dict[int, str] = {}
        self._path_to_wd: dict[str, int] = {}
        self._initialized: bool = False

        libc_name = ctypes.util.find_library("c") or "libc.so.6"
        try:
            self._libc = ctypes.CDLL(libc_name, use_errno=True)
            self._libc.inotify_init1.argtypes = [ctypes.c_int]
            self._libc.inotify_init1.restype = ctypes.c_int
            self._libc.inotify_add_watch.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_uint32]
            self._libc.inotify_add_watch.restype = ctypes.c_int
            self._libc.inotify_rm_watch.argtypes = [ctypes.c_int, ctypes.c_int]
            self._libc.inotify_rm_watch.restype = ctypes.c_int
            self._initialized = True
        except (OSError, AttributeError, ValueError, TypeError) as e:
            logger.warning(f"Failed to load libc inotify bindings: {e}")
            self._initialized = False

    def is_available(self) -> bool:
        return self._initialized and self._libc is not None

    def _ensure_fd(self) -> int:
        if self._libc is None or not self._initialized:
            raise RuntimeError("Linux inotify is not available.")
        if self._fd is None:
            fd = int(self._libc.inotify_init1(IN_CLOEXEC | IN_NONBLOCK))
            if fd < 0:
                errno = ctypes.get_errno()
                raise OSError(errno, f"inotify_init1 failed: {os.strerror(errno)}")
            self._fd = fd
        return self._fd

    def _resolve_path(self, path: str) -> str:
        scoped = ScopedPath(root=Path.home())
        return str(scoped.resolve(path.strip() or "."))

    def _parse_mask(self, mask: int | str | list[str]) -> int:
        if isinstance(mask, int):
            return mask
        if isinstance(mask, str):
            mask_lower = mask.strip().lower()
            if mask_lower in ALIAS_TO_MASK:
                return ALIAS_TO_MASK[mask_lower]
            tokens = [t.strip().lower() for t in mask_lower.split(",") if t.strip()]
        else:
            tokens = [str(t).strip().lower() for t in mask if str(t).strip()]

        result_mask = 0
        for token in tokens:
            if token in ALIAS_TO_MASK:
                result_mask |= ALIAS_TO_MASK[token]
            else:
                flag_name = token.upper()
                if not flag_name.startswith("IN_"):
                    flag_name = f"IN_{flag_name}"
                for bit, name in EVENT_NAME_MAP.items():
                    if name == flag_name:
                        result_mask |= bit
                        break
        return result_mask if result_mask > 0 else IN_ALL_EVENTS

    def add_watch(self, path: str, events: int | str | list[str] = "all", recursive: bool = False) -> dict[str, Any]:
        fd = self._ensure_fd()
        if self._libc is None:
            return {"success": False, "error": "Linux inotify is not available."}
        target_path = self._resolve_path(path)
        if not os.path.exists(target_path):
            return {"success": False, "error": f"Path '{target_path}' does not exist."}

        mask_int = self._parse_mask(events)
        added_watches = []
        paths_to_watch = [target_path]
        if recursive and os.path.isdir(target_path):
            for root, dirs, _ in os.walk(target_path):
                for d in dirs:
                    paths_to_watch.append(os.path.join(root, d))

        for p in paths_to_watch:
            wd = self._libc.inotify_add_watch(fd, p.encode("utf-8"), mask_int)
            if wd < 0:
                continue
            self._watches[wd] = p
            self._path_to_wd[p] = wd
            added_watches.append({"watch_id": wd, "path": p, "is_dir": os.path.isdir(p), "mask": mask_int})

        if not added_watches:
            return {"success": False, "error": f"Failed to watch '{target_path}'."}

        return {
            "success": True,
            "root_path": target_path,
            "watches_count": len(added_watches),
            "watches": added_watches,
        }

    def remove_watch(self, watch: int | str) -> dict[str, Any]:
        if self._fd is None or self._libc is None:
            return {"success": False, "error": "No active inotify session."}
        if isinstance(watch, int) or (isinstance(watch, str) and watch.isdigit()):
            wd = int(watch)
            path = self._watches.get(wd, "")
        else:
            path = self._resolve_path(str(watch))
            wd = self._path_to_wd.get(path, -1)

        if wd not in self._watches:
            return {"success": False, "error": f"Watch '{watch}' not found."}

        ret = self._libc.inotify_rm_watch(self._fd, wd)
        if ret < 0:
            errno = ctypes.get_errno()
            return {"success": False, "error": f"inotify_rm_watch failed: {os.strerror(errno)}"}

        self._watches.pop(wd, None)
        self._path_to_wd.pop(path, None)
        return {"success": True, "removed_watch_id": wd, "path": path}

    def list_watches(self) -> list[dict[str, Any]]:
        return [
            {
                "watch_id": wd,
                "path": p,
                "is_dir": os.path.isdir(p) if os.path.exists(p) else False,
                "exists": os.path.exists(p),
            }
            for wd, p in self._watches.items()
        ]

    def read_events(self, timeout_ms: int = 100, max_events: int = 100) -> list[dict[str, Any]]:
        if self._fd is None:
            return []
        timeout_sec = max(0.0, timeout_ms / 1000.0)
        readable, _, _ = select.select([self._fd], [], [], timeout_sec)
        if not readable:
            return []

        events = []
        with contextlib.suppress(OSError, AttributeError, ValueError, TypeError, struct.error):
            raw_data = os.read(self._fd, 16384)
            offset = 0
            data_len = len(raw_data)
            while offset + 16 <= data_len and len(events) < max_events:
                wd, mask, cookie, name_len = struct.unpack_from("iIII", raw_data, offset)
                offset += 16
                name = ""
                if name_len > 0 and offset + name_len <= data_len:
                    name = raw_data[offset : offset + name_len].decode("utf-8", errors="replace").rstrip("\x00")
                    offset += name_len

                event_flags = [flag_name for bit, flag_name in EVENT_NAME_MAP.items() if mask & bit]
                primary_event = event_flags[0] if event_flags else "UNKNOWN"
                primary_name = primary_event.removeprefix("IN_")

                watch_path = self._watches.get(wd, "")
                full_path = os.path.join(watch_path, name) if watch_path and name else (watch_path or name)

                events.append({
                    "watch_id": wd, "watch_path": watch_path, "name": name, "full_path": full_path,
                    "event": primary_name, "event_flags": event_flags, "is_dir": bool(mask & IN_ISDIR),
                    "cookie": cookie, "timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
                })
        return events

    def wait_for_event(
        self,
        path: str,
        events: int | str | list[str] = "all",
        timeout_seconds: float = 5.0,
    ) -> dict[str, Any]:
        target_path = self._resolve_path(path)
        is_already_watched = target_path in self._path_to_wd
        _ = self.read_events(timeout_ms=0, max_events=100)

        if not is_already_watched:
            watch_res = self.add_watch(target_path, events=events, recursive=False)
            if not watch_res.get("success"):
                return {"success": False, "error": watch_res.get("error")}
            temp_wd = watch_res["watches"][0]["watch_id"]
        else:
            temp_wd = None

        target_wd = temp_wd if temp_wd is not None else self._path_to_wd.get(target_path)
        start_time = time.time()
        deadline = start_time + max(0.1, timeout_seconds)

        try:
            while time.time() < deadline:
                remaining_ms = int(max(10, (deadline - time.time()) * 1000))
                evs = self.read_events(timeout_ms=min(remaining_ms, 250), max_events=10)
                for ev in evs:
                    if ev.get("event") == "IGNORED":
                        continue
                    if target_wd is None or ev.get("watch_id") == target_wd:
                        return {
                            "success": True,
                            "triggered": True,
                            "elapsed_seconds": round(time.time() - start_time, 3),
                            "event": ev,
                        }
            return {
                "success": True,
                "triggered": False,
                "timeout": True,
                "elapsed_seconds": round(time.time() - start_time, 3),
                "message": f"Timeout waiting for event on '{target_path}'.",
            }
        finally:
            if temp_wd is not None:
                self.remove_watch(temp_wd)


inotify_api = InotifyAPI()


class FileIO:
    """File reader, writer, in-place editor, and POSIX filesystem interface."""

    def _resolve(self, path: str) -> Path:
        scoped = ScopedPath(root=Path.home())
        return scoped.resolve(path or ".")

    def getcwd(self) -> str:
        return os.getcwd()

    def chdir(self, path: str) -> str:
        target = self._resolve(path)
        if not target.exists():
            return f"Error: Directory '{target}' does not exist."
        if not target.is_dir():
            return f"Error: '{target}' is not a directory."
        try:
            os.chdir(target)
            return f"Working directory changed to: {os.getcwd()}"
        except (OSError, ValueError, TypeError) as e:
            return f"Error changing directory: {e}"

    def stat(self, path: str) -> dict[str, Any]:
        try:
            file_path = self._resolve(path)
            if not file_path.exists():
                return {"error": f"Path '{file_path}' does not exist."}
            st = os.stat(file_path)
            return {
                "path": str(file_path),
                "is_dir": stat.S_ISDIR(st.st_mode),
                "is_file": stat.S_ISREG(st.st_mode),
                "is_symlink": file_path.is_symlink(),
                "permissions_octal": oct(stat.S_IMODE(st.st_mode)),
                "size_bytes": st.st_size,
                "uid": st.st_uid,
                "gid": st.st_gid,
                "mtime_iso": time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(st.st_mtime)),
                "ctime_iso": time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(st.st_ctime)),
                "inode": st.st_ino,
            }
        except (OSError, ValueError, TypeError) as e:
            return {"error": f"Error querying stat: {e}"}

    def chmod(self, path: str, mode: str | int) -> str:
        try:
            file_path = self._resolve(path)
            if not file_path.exists():
                return f"Error: Path '{file_path}' does not exist."
            mode_int = int(mode.strip(), 8) if isinstance(mode, str) else int(mode)
            os.chmod(file_path, mode_int)
            mode_oct = oct(stat.S_IMODE(os.stat(file_path).st_mode))
            return f"Successfully changed permissions of '{file_path}' to {mode_oct}."
        except (OSError, ValueError, TypeError) as e:
            return f"Error changing permissions: {e}"

    def disk_usage(self, path: str = ".") -> dict[str, Any]:
        try:
            target = self._resolve(path)
            usage = shutil.disk_usage(target)
            total, used, free = usage.total, usage.used, usage.free
            used_pct = round((used / total * 100), 2) if total > 0 else 0.0
            result = {
                "target_path": str(target),
                "total_gb": round(total / (1024**3), 2),
                "used_gb": round(used / (1024**3), 2),
                "free_gb": round(free / (1024**3), 2),
                "used_percentage": f"{used_pct}%",
            }
            if hasattr(os, "statvfs"):
                with contextlib.suppress(OSError, AttributeError):
                    st = os.statvfs(target)
                    result["total_inodes"] = st.f_files
                    result["free_inodes"] = st.f_ffree
            return result
        except (OSError, ValueError, TypeError) as e:
            return {"error": f"Error querying disk usage: {e}"}

    def list_mounts(self) -> list[dict[str, Any]]:
        mounts_path = Path("/proc/mounts")
        if not mounts_path.exists():
            return []
        mounts = []
        min_parts = 4
        virtual_fs = ("sysfs", "proc", "devtmpfs", "devpts", "tmpfs", "cgroup", "cgroup2", "pstore", "bpf", "tracefs")
        try:
            with open(mounts_path, encoding="utf-8", errors="replace") as f:
                for line in f:
                    parts = line.strip().split()
                    if len(parts) >= min_parts:
                        dev, mp, fs, opts = parts[0], parts[1], parts[2], parts[3]
                        if fs in virtual_fs:
                            continue
                        mounts.append({"device": dev, "mount_point": mp, "fs_type": fs, "options": opts})
        except (OSError, ValueError, TypeError):
            pass
        return mounts

    def get_all_disks(self) -> dict[str, Any]:
        mounts = self.list_mounts()
        disk_overview = []
        seen = set()
        for m in mounts:
            target = m["mount_point"]
            if target in seen:
                continue
            seen.add(target)
            usage = self.disk_usage(target)
            if "error" not in usage:
                usage["device"], usage["fs_type"] = m["device"], m["fs_type"]
                disk_overview.append(usage)
        return {"mounted_disks": disk_overview, "total_mounts_scanned": len(disk_overview)}

    def read(self, path: str, start_line: int | None = None, end_line: int | None = None) -> str:
        file_path = self._resolve(path)
        if not file_path.exists():
            return f"Error: File '{file_path}' does not exist."
        if file_path.is_dir():
            return f"Error: '{file_path}' is a directory."
        try:
            with open(file_path, encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
            if start_line is not None or end_line is not None:
                start = max(1, start_line or 1) - 1
                end = min(len(lines), end_line or len(lines))
                return "".join([f"{start + i + 1}: {line}" for i, line in enumerate(lines[start:end])])
            return "".join(lines)
        except (OSError, ValueError, TypeError) as e:
            return f"Error reading file: {e}"

    def write(self, path: str, content: str, atomic: bool = True) -> str:
        file_path = self._resolve(path)
        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            if atomic:
                with tempfile.NamedTemporaryFile("w", dir=str(file_path.parent), delete=False, encoding="utf-8") as tf:
                    tf.write(content)
                    temp_name = tf.name
                shutil.move(temp_name, str(file_path))
            else:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(content)
            return f"Successfully wrote {len(content)} characters to '{file_path}'."
        except (OSError, ValueError, TypeError) as e:
            return f"Error writing to file: {e}"

    def replace(self, path: str, target: str, replacement: str) -> str:
        file_path = self._resolve(path)
        if not file_path.exists():
            return f"Error: File '{file_path}' does not exist."
        try:
            with open(file_path, encoding="utf-8", errors="replace") as f:
                content = f.read()
            if target not in content:
                return f"Error: Target text not found in '{file_path}'."
            count = content.count(target)
            new_content = content.replace(target, replacement, 1)
            self.write(str(file_path), new_content, atomic=True)
            return f"Successfully replaced block in '{file_path}' (match 1 of {count})."
        except (OSError, ValueError, TypeError) as e:
            return f"Error replacing in file: {e}"

    def list_dir(self, path: str = ".", recursive: bool = False, max_items: int = 50) -> list[dict[str, Any]]:
        dir_path = self._resolve(path)
        if not dir_path.exists() or not dir_path.is_dir():
            return [{"error": f"Directory '{dir_path}' does not exist."}]
        results = []
        try:
            with os.scandir(dir_path) as it:
                for entry in it:
                    is_d = entry.is_dir(follow_symlinks=False)
                    st = entry.stat(follow_symlinks=False)
                    results.append({
                        "name": entry.name, "type": "directory" if is_d else "file",
                        "size_bytes": st.st_size if not is_d else 0,
                        "permissions": oct(stat.S_IMODE(st.st_mode)),
                        "mtime": time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(st.st_mtime)),
                        "path": entry.path,
                    })
                    if len(results) >= max_items:
                        break
            return results
        except (OSError, ValueError, TypeError) as e:
            return [{"error": str(e)}]

    def find(self, directory: str, pattern: str, max_results: int = 30) -> list[str]:
        dir_path = self._resolve(directory)
        matches = []
        try:
            for root, _, files in os.walk(dir_path):
                for f in files:
                    if fnmatch.fnmatch(f, pattern):
                        matches.append(os.path.join(root, f))
                        if len(matches) >= max_results:
                            return matches
            return matches
        except (OSError, ValueError, TypeError) as e:
            return [f"Error searching: {e}"]


file_io = FileIO()


class FilesystemStorage(Yarn):
    def is_available(self) -> bool:
        return True

    @strand(
        description="Read contents of a text file with optional start and end line ranges.",
        tier=CapabilityTier.OBSERVE,
    )
    def file_read(self, path: str, start_line: int | None = None, end_line: int | None = None) -> str:
        """Read contents of a text file with optional start and end line ranges.

        :param path: Target file path.
        :param start_line: Optional start line (1-indexed).
        :param end_line: Optional end line (1-indexed).
        """
        return file_io.read(path, start_line=start_line, end_line=end_line)

    @strand(description="Write or overwrite text content to a target file path.", tier=CapabilityTier.MUTATE)
    def file_write(self, path: str, content: str) -> str:
        """Write or overwrite text content to a target file path.

        :param path: Target file path.
        :param content: Text content to write.
        """
        return file_io.write(path, content=content, atomic=True)

    @strand(description="Replace exact text substring within a target file.", tier=CapabilityTier.MUTATE)
    def file_replace(self, path: str, target: str, replacement: str = "") -> str:
        """Replace exact text substring within a target file.

        :param path: Target file path.
        :param target: Exact text substring to replace.
        :param replacement: Replacement text substring.
        """
        return file_io.replace(path, target=target, replacement=replacement)

    @strand(description="List files and directories within a target directory path.")
    def file_list(self, path: str = ".") -> list[dict[str, Any]]:
        """List files and directories within a target directory path.

        :param path: Target directory path (default: current directory).
        """
        return file_io.list_dir(path or ".")

    @strand(description="Search for files matching a glob pattern in a directory path.")
    def file_find(self, path: str = ".", pattern: str = "*") -> list[str]:
        """Search for files matching a glob pattern in a directory path.

        :param path: Search root directory path.
        :param pattern: Glob search pattern (e.g. '*.py', '*.json').
        """
        return file_io.find(path or ".", pattern=pattern or "*")

    @strand(description="Get stat metadata, permissions, size, and timestamps for a file path.")
    def file_stat(self, path: str) -> dict[str, Any]:
        """Get stat metadata, permissions, size, and timestamps for a file path.

        :param path: Target file or directory path.
        """
        return file_io.stat(path)

    @strand(description="Change permissions mode for a file or directory path.")
    def file_chmod(self, path: str, mode: str) -> str:
        """Change permissions mode for a file or directory path.

        :param path: Target file or directory path.
        :param mode: Permissions octal string (e.g. '755', '644').
        """
        return file_io.chmod(path, mode=mode)

    @strand(description="Get total, used, and available disk usage for a storage path.")
    def storage_disk_usage(self, path: str = "/") -> dict[str, Any]:
        """Get total, used, and available disk usage for a storage path.

        :param path: Mount or directory path.
        """
        return file_io.disk_usage(path or "/")

    @strand(description="List mounted filesystems and storage devices.")
    def storage_list_mounts(self) -> list[dict[str, Any]]:
        """List mounted filesystems and storage devices."""
        return file_io.list_mounts()

    @strand(description="File system operations, directory navigation, permissions, and disk usage.")
    def file_op(
        self,
        operation: Literal[
            "read", "write", "replace", "list", "find", "getcwd", "chdir",
            "stat", "chmod", "disk_usage", "list_mounts", "get_all_disks",
            "watch", "unwatch", "list_watches", "read_events", "wait_event"
        ],
        path: str | None = None,
        content: str | None = None,
        target: str | None = None,
        replacement: str | None = "",
        mode: str | None = None,
        start_line: int | None = None,
        end_line: int | None = None,
        pattern: str | None = "*",
        events: str | None = "all",
        recursive: bool = False,
        timeout_seconds: float = 5.0,
    ) -> Any:
        """Pure Python native file reader, writer, replacer, directory navigator, stat, chmod, disk usage, and inotify.

        :param operation: File/Directory/Storage operation.
        :param path: Target path.
        :param content: Content to write.
        :param target: Text to replace.
        :param replacement: Replacement text.
        :param mode: Permissions octal (e.g. '755').
        :param start_line: Start line (1-indexed).
        :param end_line: End line (1-indexed).
        :param pattern: Glob search pattern.
        :param events: inotify mask ('all', 'modify', 'create', 'delete', 'write', 'move').
        :param recursive: Recursive watch flag.
        :param timeout_seconds: Timeout in seconds.
        """
        op = str(operation).strip().lower()
        raw_path = str(path or "").strip()
        cnt = str(content or "")
        tgt = str(target or "")
        repl = str(replacement or "")
        m = str(mode or "")
        pat = str(pattern or "*").strip()
        evts = str(events or "all").strip()

        handlers = {
            "getcwd": lambda: f"Current working directory: {file_io.getcwd()}",
            "chdir": lambda: file_io.chdir(raw_path or "."),
            "read": lambda: file_io.read(raw_path, start_line=start_line, end_line=end_line),
            "write": lambda: file_io.write(raw_path, content=cnt, atomic=True),
            "replace": lambda: file_io.replace(raw_path, target=tgt, replacement=repl),
            "list": lambda: file_io.list_dir(raw_path or "."),
            "find": lambda: file_io.find(raw_path or ".", pattern=pat),
            "stat": lambda: file_io.stat(raw_path or "."),
            "chmod": lambda: file_io.chmod(raw_path, mode=m),
            "disk_usage": lambda: file_io.disk_usage(raw_path or "."),
            "statvfs": lambda: file_io.disk_usage(raw_path or "."),
            "df": lambda: file_io.disk_usage(raw_path or "."),
            "list_mounts": file_io.list_mounts,
            "mounts": file_io.list_mounts,
            "get_all_disks": file_io.get_all_disks,
            "all_disks": file_io.get_all_disks,
            "disks": file_io.get_all_disks,
            "watch": lambda: inotify_api.add_watch(raw_path or ".", events=evts, recursive=recursive),
            "unwatch": lambda: inotify_api.remove_watch(raw_path),
            "list_watches": inotify_api.list_watches,
            "read_events": lambda: inotify_api.read_events(timeout_ms=int(timeout_seconds * 1000)),
            "wait_event": lambda: inotify_api.wait_for_event(
                raw_path or ".", events=evts, timeout_seconds=timeout_seconds
            ),
        }
        if op in handlers:
            return handlers[op]()
        return f"Unknown file operation '{op}'."

    @strand(description="Add a Linux inotify kernel watch on a file or directory.")
    def inotify_watch(self, path: str, events: str = "all", recursive: bool = False) -> dict[str, Any]:
        """Add a Linux inotify kernel watch on a file or directory.

        :param path: Target path.
        :param events: Event mask or comma-separated list.
        :param recursive: Recursive watch flag.
        """
        return inotify_api.add_watch(path.strip(), events=events, recursive=recursive)

    @strand(description="Wait synchronously for a specific filesystem event on a path.")
    def inotify_wait_event(self, path: str, events: str = "all", timeout_seconds: float = 5.0) -> dict[str, Any]:
        """Wait synchronously for a specific filesystem event on a path.

        :param path: Target path.
        :param events: Event mask.
        :param timeout_seconds: Timeout in seconds.
        """
        return inotify_api.wait_for_event(path.strip(), events=events, timeout_seconds=timeout_seconds)

    @strand(description="Poll and read available inotify kernel events from active watches.")
    def inotify_read_events(self, timeout_ms: int = 100, max_events: int = 50) -> list[dict[str, Any]]:
        """Poll and read available inotify kernel events from active watches.

        :param timeout_ms: Timeout in ms.
        :param max_events: Max events to return.
        """
        return inotify_api.read_events(timeout_ms=timeout_ms, max_events=max_events)

    @strand(description="Remove an active inotify watch by descriptor ID or path.")
    def inotify_unwatch(self, watch: str) -> dict[str, Any]:
        """Remove an active inotify watch by descriptor ID or path.

        :param watch: Watch descriptor ID or path.
        """
        return inotify_api.remove_watch(watch)

    @strand(description="List all active inotify watch descriptors and paths.")
    def inotify_list_watches(self) -> list[dict[str, Any]]:
        """List all active inotify watch descriptors and paths."""
        return inotify_api.list_watches()
