"""
Unit tests for Textile Bubblewrap Sandbox and Hem integration.
"""

import asyncio
import os
import sys
import tempfile
import unittest.mock
from pathlib import Path

import hem
import pytest
from hem import BubblewrapBuilder, apply_resources, wrap_command

from textile.core.security.sandbox import create_sandbox_builder


class TestBubblewrapSandbox:
    def test_bwrap_availability(self):
        # On this system bwrap is installed
        if sys.platform == "linux":
            assert hem.is_available() is True

    def test_wrap_command_read_only(self):
        cmd = ["python", "-c", "print(1)"]
        wrapped = wrap_command(cmd, writable=False, workspace="/tmp/test_ws")
        assert "bwrap" in wrapped[0]
        assert "--unshare-user" in wrapped
        assert "--ro-bind" in wrapped
        assert "/tmp/test_ws" in wrapped
        assert "--tmpfs" in wrapped
        assert "/home" in wrapped

    def test_wrap_command_writable(self):
        cmd = ["python", "-c", "print(1)"]
        wrapped = wrap_command(cmd, writable=True, workspace="/tmp/test_ws")
        assert "bwrap" in wrapped[0]
        assert "--bind" in wrapped
        assert "/tmp/test_ws" in wrapped

    def test_bwrap_enforces_read_only_and_hides_home(self):
        if not hem.is_available():
            pytest.skip("bwrap not available")

        with tempfile.TemporaryDirectory() as tmpdir:
            f = Path(tmpdir) / "test.txt"
            f.write_text("observe this", encoding="utf-8")

            # In read-only mode, reading succeeds
            read_cmd = [sys.executable, "-c", f'print(open("{f}").read())']
            builder_read = create_sandbox_builder(read_cmd, writable=False, workspace_root=tmpdir)

            res_read = builder_read.run(read_cmd, capture_output=True, text=True, check=False)
            assert res_read.returncode == 0
            assert "observe this" in res_read.stdout

            # Test async_run on builder
            res_async = asyncio.run(builder_read.async_run(read_cmd, capture_output=True, text=True, check=False))
            assert res_async.returncode == 0
            assert "observe this" in res_async.stdout

            # In read-only mode, writing fails with Read-only file system
            write_cmd = [sys.executable, "-c", f'open("{f}", "w").write("fail")']
            builder_write = create_sandbox_builder(write_cmd, writable=False, workspace_root=tmpdir)
            res_write = builder_write.run(write_cmd, capture_output=True, text=True, check=False)
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
                wrapped = wrap_command(cmd, writable=False, workspace="/tmp", resources=["display", "invalid-resource"])
                assert "--ro-bind" in wrapped
                assert dummy_sock.name in wrapped
                assert "--setenv" in wrapped
                assert "WAYLAND_DISPLAY" in wrapped

    def test_apply_declarative_sandbox_resources(self):
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
                builder = BubblewrapBuilder("bwrap")
                apply_resources(
                    builder,
                    [
                        "display:wayland",
                        "dbus:session",
                        "socket:$XDG_RUNTIME_DIR/test.sock",
                        "env:TEST_CUSTOM_ENV",
                        "env:STATIC_VAL=123",
                    ],
                )
                args = builder.args
                assert "--setenv" in args
                assert "WAYLAND_DISPLAY" in args
                assert "DBUS_SESSION_BUS_ADDRESS" in args
                assert "TEST_CUSTOM_ENV" in args
                assert "STATIC_VAL" in args
                assert str(sock_file) in args

    def test_bubblewrap_builder_primitives(self):
        builder = (
            BubblewrapBuilder("/usr/bin/bwrap")
            .clearenv()
            .setenv("FOO", "BAR")
            .unsetenv("BAZ")
            .ro_bind("/etc", try_ok=True)
            .bind("/tmp")
            .dev_bind("/dev/null")
            .tmpfs("/run")
            .dev("/dev")
            .proc("/proc")
            .symlink("usr/bin", "/bin")
            .dir("/var/log")
            .chdir("/tmp")
            .unshare("user", "net")
            .die_with_parent()
        )
        cmd = builder.build(["echo", "hello"])

        assert cmd[0] == "/usr/bin/bwrap"
        assert "--clearenv" in cmd
        assert cmd[2:5] == ["--setenv", "FOO", "BAR"]
        assert cmd[5:7] == ["--unsetenv", "BAZ"]
        assert cmd[7:10] == ["--ro-bind-try", "/etc", "/etc"]
        assert cmd[10:13] == ["--bind", "/tmp", "/tmp"]
        assert cmd[13:16] == ["--dev-bind", "/dev/null", "/dev/null"]
        assert cmd[16:18] == ["--tmpfs", "/run"]
        assert cmd[18:20] == ["--dev", "/dev"]
        assert cmd[20:22] == ["--proc", "/proc"]
        assert cmd[22:25] == ["--symlink", "usr/bin", "/bin"]
        assert cmd[25:27] == ["--dir", "/var/log"]
        assert cmd[27:29] == ["--chdir", "/tmp"]
        assert "--unshare-user" in cmd
        assert "--unshare-net" in cmd
        assert "--die-with-parent" in cmd
        assert cmd[-2:] == ["echo", "hello"]
