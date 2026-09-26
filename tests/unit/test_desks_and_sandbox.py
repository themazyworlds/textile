"""
Unit tests for Textile Tier Passes & Desks (Object Capabilities) and Landlock Sandbox.
"""

import sys
import tempfile
import unittest.mock
from pathlib import Path

import pytest

from textile.core.desks import InteractDesk, MutateDesk, ObserverDesk
from textile.core.guardrails import AccessBoundaryError
from textile.core.sandbox import BubblewrapSandbox, LandlockSandbox
from textile.core.transaction import transaction_stack


class TestTierPassDesks:

    def test_observer_desk_read_within_boundary(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            f = root / "data.txt"
            f.write_text("hello observer", encoding="utf-8")

            desk = ObserverDesk(root=root)
            content = desk.read_text("data.txt")
            assert content == "hello observer"

            entries = desk.list_dir(".")
            assert "data.txt" in entries

            st = desk.stat("data.txt")
            assert st["size_bytes"] == len("hello observer")
            assert st["is_dir"] is False

    def test_observer_desk_cannot_escape_root(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            desk = ObserverDesk(root=root)

            with pytest.raises(AccessBoundaryError):
                desk.read_text("../../etc/shadow")

    def test_observer_desk_lacks_write_methods(self):
        desk = ObserverDesk()
        assert not hasattr(desk, "write_text")
        assert not hasattr(desk, "create_dir")
        assert not hasattr(desk, "delete_file")

    def test_interact_desk_has_notify_and_reads(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            f = root / "ui.txt"
            f.write_text("ui state", encoding="utf-8")

            desk = InteractDesk(root=root)
            assert desk.read_text("ui.txt") == "ui state"
            msg = desk.notify("Hello World", title="Test")
            assert "Hello World" in msg
            assert not hasattr(desk, "write_text")

    def test_mutate_desk_writes_and_registers_rollback(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            desk = MutateDesk(root=root)

            transaction_stack.clear()
            p = desk.write_text("output.txt", "mutation 1")
            assert p.read_text() == "mutation 1"

            # Check that transaction stack recorded the mutation
            assert len(transaction_stack._stack) >= 1
            assert transaction_stack._stack[-1].strand_name == "desk_write_text"

            # Test undo rollback restores state
            success, _ = transaction_stack.undo_last()
            assert success is True
            assert not p.exists()  # deleted since it did not exist before


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
            read_cmd = ["python3", "-c", f'print(open("{f}").read())']
            wrapped_read = BubblewrapSandbox.wrap_command(read_cmd, tier="OBSERVE", workspace_root=tmpdir)
            import subprocess
            res_read = subprocess.run(wrapped_read, capture_output=True, text=True, check=False)
            assert res_read.returncode == 0
            assert "observe this" in res_read.stdout

            # In OBSERVE mode, writing fails with Read-only file system
            write_cmd = ["python3", "-c", f'open("{f}", "w").write("fail")']
            wrapped_write = BubblewrapSandbox.wrap_command(write_cmd, tier="OBSERVE", workspace_root=tmpdir)
            res_write = subprocess.run(wrapped_write, capture_output=True, text=True, check=False)
            assert res_write.returncode != 0
            assert "Read-only file system" in res_write.stderr

    def test_wrap_command_known_resources(self):
        cmd = ["echo", "test"]
        with unittest.mock.patch.dict("os.environ", {"DBUS_SESSION_BUS_ADDRESS": "unix:path=/tmp/test_bus.sock"}):
            with tempfile.NamedTemporaryFile(suffix=".sock") as dummy_sock:
                dummy_addr = f"unix:path={dummy_sock.name}"
                with unittest.mock.patch.dict("os.environ", {"DBUS_SESSION_BUS_ADDRESS": dummy_addr}):
                    wrapped = BubblewrapSandbox.wrap_command(
                        cmd, tier="OBSERVE", workspace_root="/tmp", resources=["dbus-session", "invalid-resource"]
                    )
                    assert "--ro-bind" in wrapped
                    assert dummy_sock.name in wrapped
                    assert "--setenv" in wrapped
                    assert "DBUS_SESSION_BUS_ADDRESS" in wrapped

