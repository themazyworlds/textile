"""
Bubblewrap (bwrap) Command Builder.
Pure-Python, type-safe, fluent builder for Linux unprivileged container execution arguments.
Decoupled from application-specific logic so it can be used standalone or extracted into a package.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Self


class BubblewrapBuilder:
    """Fluent, type-safe builder for constructing Bubblewrap (bwrap) execution arguments."""

    def __init__(self, bwrap_path: str | Path | None = None) -> None:
        resolved_bwrap = str(bwrap_path) if bwrap_path else (shutil.which("bwrap") or "bwrap")
        self._args: list[str] = [resolved_bwrap]

    @property
    def args(self) -> list[str]:
        """Return the current list of CLI argument tokens."""
        return list(self._args)

    def clearenv(self) -> Self:
        """Unset all environment variables inside container."""
        self._args.append("--clearenv")
        return self

    def setenv(self, key: str, value: str | None) -> Self:
        """Set environment variable inside container."""
        if value is not None:
            self._args.extend(["--setenv", str(key), str(value)])
        return self

    def unsetenv(self, key: str) -> Self:
        """Unset specified environment variable inside container."""
        self._args.extend(["--unsetenv", str(key)])
        return self

    def ro_bind(self, src: str | Path, dest: str | Path | None = None, *, try_ok: bool = False) -> Self:
        """Bind source directory or file as read-only inside the container."""
        src_str = str(src)
        dest_str = str(dest) if dest is not None else src_str
        flag = "--ro-bind-try" if try_ok else "--ro-bind"
        self._args.extend([flag, src_str, dest_str])
        return self

    def bind(self, src: str | Path, dest: str | Path | None = None, *, try_ok: bool = False) -> Self:
        """Bind source directory or file as read-write inside the container."""
        src_str = str(src)
        dest_str = str(dest) if dest is not None else src_str
        flag = "--bind-try" if try_ok else "--bind"
        self._args.extend([flag, src_str, dest_str])
        return self

    def dev_bind(self, src: str | Path, dest: str | Path | None = None, *, try_ok: bool = False) -> Self:
        """Bind source device node inside the container."""
        src_str = str(src)
        dest_str = str(dest) if dest is not None else src_str
        flag = "--dev-bind-try" if try_ok else "--dev-bind"
        self._args.extend([flag, src_str, dest_str])
        return self

    def tmpfs(self, dest: str | Path) -> Self:
        """Mount a clean tmpfs filesystem at the destination path."""
        self._args.extend(["--tmpfs", str(dest)])
        return self

    def dev(self, dest: str | Path = "/dev") -> Self:
        """Mount a minimal /dev filesystem containing standard device nodes."""
        self._args.extend(["--dev", str(dest)])
        return self

    def proc(self, dest: str | Path = "/proc") -> Self:
        """Mount a clean /proc filesystem at destination."""
        self._args.extend(["--proc", str(dest)])
        return self

    def symlink(self, target: str | Path, link_name: str | Path) -> Self:
        """Create a symbolic link inside the container filesystem."""
        self._args.extend(["--symlink", str(target), str(link_name)])
        return self

    def dir(self, path: str | Path) -> Self:
        """Create a directory inside the container."""
        self._args.extend(["--dir", str(path)])
        return self

    def chdir(self, path: str | Path) -> Self:
        """Set working directory inside the container."""
        self._args.extend(["--chdir", str(path)])
        return self

    def die_with_parent(self, enabled: bool = True) -> Self:
        """Ensure the container process terminates automatically if calling process exits."""
        if enabled:
            self._args.append("--die-with-parent")
        return self

    def unshare_all(self) -> Self:
        """Unshare all available namespaces (user, pid, net, ipc, uts, cgroup)."""
        self._args.append("--unshare-all")
        return self

    def unshare(self, *namespaces: str) -> Self:
        """Selectively unshare specific Linux kernel namespaces (e.g. 'user', 'pid', 'net', 'ipc', 'uts', 'cgroup')."""
        for ns in namespaces:
            clean_ns = ns.strip().lstrip("-").replace("_", "-")
            if not clean_ns.startswith("unshare-"):
                clean_ns = f"unshare-{clean_ns}"
            self._args.append(f"--{clean_ns}")
        return self

    def share_net(self) -> Self:
        """Retain host network access even when unsharing namespaces."""
        self._args.append("--share-net")
        return self

    # High-level standard system assembly methods
    def bind_system_base(self) -> Self:
        """Mount system binaries, libraries, standard symlinks, and minimal dev/proc."""
        self.ro_bind("/usr")
        lib64_target = "usr/lib64" if Path("/usr/lib64").exists() else "usr/lib"
        self.symlink(lib64_target, "/lib64")
        self.symlink("usr/lib", "/lib")
        self.symlink("usr/bin", "/bin")
        self.symlink("usr/bin", "/sbin")

        for sys_dir in ("/etc", "/sys", "/opt", "/nix"):
            self.ro_bind(sys_dir, try_ok=True)

        self.dev("/dev").proc("/proc")
        return self

    def bind_tmpfs_paths(self, paths: list[str | Path]) -> Self:
        """Mount empty tmpfs at multiple paths."""
        for p in paths:
            self.tmpfs(p)
        return self

    def set_namespaces(self, allow_network: bool = False, unshare_user: bool = True) -> Self:
        """Configure standard execution namespaces with deterministic parent termination."""
        ns: list[str] = ["ipc", "uts"]
        if unshare_user:
            ns.extend(["user", "pid"])
        if not allow_network:
            ns.append("net")
        self.unshare(*ns)
        self.die_with_parent()
        return self

    def bind_workspace(self, workspace: str | Path, writable: bool = False) -> Self:
        """Bind workspace directory and set as container working directory."""
        ws_path = Path(workspace).resolve()
        if writable:
            self.bind(ws_path)
        else:
            self.ro_bind(ws_path)
        self.chdir(ws_path)
        return self

    def build(self, target_cmd: list[str] | None = None) -> list[str]:
        """Compile the complete Bubblewrap command tokens, appending target executable command."""
        return list(self._args) + (list(target_cmd) if target_cmd else [])
