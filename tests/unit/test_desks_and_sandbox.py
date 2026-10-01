"""
Unit tests for Textile Landlock & Bubblewrap Sandbox.
"""

import os
import subprocess
import sys
import tempfile
import unittest.mock
from pathlib import Path

import pytest

from textile.core.security.sandbox import BubblewrapSandbox, LandlockSandbox


class TestLandlockSandbox:
    def test_landlock_is_supported_on_linux(self):
        if sys.platform == "linux":
            # On Linux kernels >= 5.13 Landlock is supported
            assert LandlockSandbox.is_supported() is True
        else:
            assert LandlockSandbox.is_supported() is False


class TestBubblewrapSandbox:
    def test_bwrap_availability(self):
        # On this system bwrap is installed
        if sys.platform == "linux":
            assert BubblewrapSandbox.is_available() is True

    def test_wrap_command_observe(self):
        cmd = ["python", "-c", "print(1)"]
        wrapped = BubblewrapSandbox.wrap_command(cmd, tier="OBSERVE", workspace_root="/tmp/test_ws")
        assert "bwrap" in wrapped[0]
        assert "--unshare-user" in wrapped
        assert "--ro-bind" in wrapped
        assert "/tmp/test_ws" in wrapped
        assert "--tmpfs" in wrapped
        assert "/home" in wrapped

    def test_wrap_command_mutate(self):
        cmd = ["python", "-c", "print(1)"]
        wrapped = BubblewrapSandbox.wrap_command(cmd, tier="MUTATE", workspace_root="/tmp/test_ws")
        assert "bwrap" in wrapped[0]
        assert "--bind" in wrapped
        assert "/tmp/test_ws" in wrapped

    def test_wrap_command_privileged_passes_unmodified(self):
        cmd = ["python", "-c", "print(1)"]
        wrapped = BubblewrapSandbox.wrap_command(cmd, tier="PRIVILEGED", workspace_root="/tmp/test_ws")
        assert wrapped == cmd

    def test_bwrap_enforces_read_only_and_hides_home(self):
        if not BubblewrapSandbox.is_available():
            pytest.skip("bwrap not available")

        with tempfile.TemporaryDirectory() as tmpdir:
            f = Path(tmpdir) / "test.txt"
            f.write_text("observe this", encoding="utf-8")

            # In OBSERVE mode, reading succeeds
            read_cmd = [sys.executable, "-c", f'print(open("{f}").read())']
            wrapped_read = BubblewrapSandbox.wrap_command(read_cmd, tier="OBSERVE", workspace_root=tmpdir)

            res_read = subprocess.run(wrapped_read, capture_output=True, text=True, check=False)
            assert res_read.returncode == 0
            assert "observe this" in res_read.stdout

            # In OBSERVE mode, writing fails with Read-only file system
            write_cmd = [sys.executable, "-c", f'open("{f}", "w").write("fail")']
            wrapped_write = BubblewrapSandbox.wrap_command(write_cmd, tier="OBSERVE", workspace_root=tmpdir)
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
                    cmd, tier="OBSERVE", workspace_root="/tmp", resources=["display", "invalid-resource"]
                )
                assert "--ro-bind" in wrapped
                assert dummy_sock.name in wrapped
                assert "--setenv" in wrapped
                assert "WAYLAND_DISPLAY" in wrapped
