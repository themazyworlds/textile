"""
Unit tests for Textile Bubblewrap Sandbox.
"""

import os
import subprocess
import sys
import tempfile
import unittest.mock
from pathlib import Path

import pytest

from textile.core.security.sandbox import BubblewrapSandbox


class TestBubblewrapSandbox:
    def test_bwrap_availability(self):
        # On this system bwrap is installed
        if sys.platform == "linux":
            assert BubblewrapSandbox.is_available() is True

    def test_wrap_command_read_only(self):
        cmd = ["python", "-c", "print(1)"]
        wrapped = BubblewrapSandbox.wrap_command(cmd, writable=False, workspace_root="/tmp/test_ws")
        assert "bwrap" in wrapped[0]
        assert "--unshare-user" in wrapped
        assert "--ro-bind" in wrapped
        assert "/tmp/test_ws" in wrapped
        assert "--tmpfs" in wrapped
        assert "/home" in wrapped

    def test_wrap_command_writable(self):
        cmd = ["python", "-c", "print(1)"]
        wrapped = BubblewrapSandbox.wrap_command(cmd, writable=True, workspace_root="/tmp/test_ws")
        assert "bwrap" in wrapped[0]
        assert "--bind" in wrapped
        assert "/tmp/test_ws" in wrapped

    def test_bwrap_enforces_read_only_and_hides_home(self):
        if not BubblewrapSandbox.is_available():
            pytest.skip("bwrap not available")

        with tempfile.TemporaryDirectory() as tmpdir:
            f = Path(tmpdir) / "test.txt"
            f.write_text("observe this", encoding="utf-8")

            # In read-only mode, reading succeeds
            read_cmd = [sys.executable, "-c", f'print(open("{f}").read())']
            wrapped_read = BubblewrapSandbox.wrap_command(read_cmd, writable=False, workspace_root=tmpdir)

            res_read = subprocess.run(wrapped_read, capture_output=True, text=True, check=False)
            assert res_read.returncode == 0
            assert "observe this" in res_read.stdout

            # In read-only mode, writing fails with Read-only file system
            write_cmd = [sys.executable, "-c", f'open("{f}", "w").write("fail")']
            wrapped_write = BubblewrapSandbox.wrap_command(write_cmd, writable=False, workspace_root=tmpdir)
            res_write = subprocess.run(wrapped_write, capture_output=True, text=True, check=False)
            assert res_write.returncode != 0
            assert "Read-only file system" in res_write.stderr

    def test_wrap_command_known_resources(self):
        cmd = ["echo", "test"]
        with (
            tempfile.TemporaryDirectory() as tmp_dir,
            tempfile.NamedTemporaryFile(dir=tmp_dir, suffix=".sock") as dummy_sock,
        ):
            wl_name = os.path.basename(dummy_sock.name)
            with unittest.mock.patch.dict("os.environ", {"WAYLAND_DISPLAY": wl_name, "XDG_RUNTIME_DIR": tmp_dir}):
                wrapped = BubblewrapSandbox.wrap_command(
                    cmd, writable=False, workspace_root="/tmp", resources=["display", "invalid-resource"]
                )
                assert "--ro-bind" in wrapped
                assert dummy_sock.name in wrapped
                assert "--setenv" in wrapped
                assert "WAYLAND_DISPLAY" in wrapped

    def test_resolve_declarative_sandbox_resources(self):
        from textile.core.security.sandbox import resolve_sandbox_resources

        with tempfile.TemporaryDirectory() as tmp_dir:
            sock_file = Path(tmp_dir) / "test.sock"
            sock_file.touch()

            env_vars = {
                "XDG_RUNTIME_DIR": tmp_dir,
                "WAYLAND_DISPLAY": "test.sock",
                "DBUS_SESSION_BUS_ADDRESS": f"unix:path={sock_file}",
                "TEST_CUSTOM_ENV": "active",
            }
            with unittest.mock.patch.dict("os.environ", env_vars):
                args = resolve_sandbox_resources(
                    [
                        "display:wayland",
                        "dbus:session",
                        "socket:$XDG_RUNTIME_DIR/test.sock",
                        "env:TEST_CUSTOM_ENV",
                        "env:STATIC_VAL=123",
                    ]
                )
                assert "--setenv" in args
                assert "WAYLAND_DISPLAY" in args
                assert "DBUS_SESSION_BUS_ADDRESS" in args
                assert "TEST_CUSTOM_ENV" in args
                assert "STATIC_VAL" in args
                assert str(sock_file) in args
