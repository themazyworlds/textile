"""
Unit tests for Textile Tier Passes & Desks (Object Capabilities) and Landlock Sandbox.
"""

import sys
import tempfile
from pathlib import Path

import pytest

from textile.core.desks import InteractDesk, MutateDesk, ObserverDesk
from textile.core.guardrails import AccessBoundaryError
from textile.core.sandbox import LandlockSandbox
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
