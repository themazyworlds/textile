import asyncio
import threading
import unittest
from typing import Any
from unittest.mock import MagicMock, patch

import pyotp
from hem import BubblewrapBuilder
from needle import Strand, Yarn
from needle.errors import StrandCollisionError

from textile.core.definitions.errors import SandboxUnavailableError
from textile.core.execution.invoker import execute_direct
from textile.core.execution.runner import execute_strand, execute_strand_async
from textile.core.orchestration.loom import Loom
from textile.core.security.context import OTPChallengeRequiredError, OTPManager
from textile.core.security.sandbox import create_sandbox_builder


class TestArchitectureHardening(unittest.TestCase):
    def test_totp_manager_verification_and_replay_prevention(self):
        secret = pyotp.random_base32()
        manager = OTPManager(secret=secret)

        current_code = pyotp.TOTP(secret).now()
        self.assertEqual(len(current_code), 6)

        # First verification succeeds
        self.assertTrue(manager.verify_and_consume(current_code))

        # Replay with same code in same time window fails (single-use)
        self.assertFalse(manager.verify_and_consume(current_code))

        # Invalid code fails
        self.assertFalse(manager.verify_and_consume("000000"))

    def test_execute_direct_async_handler_support(self):
        class AsyncYarn(Yarn):
            def __init__(self):
                super().__init__(name="async_yarn", layer=50)

            def is_available(self):
                return True

            def get_strands(self):
                async def _async_handler(args: dict[str, Any]) -> str:
                    await asyncio.sleep(0.001)
                    return f"async_result_{args.get('val', '')}"

                return [self.build_strand("async_tool", "Async tool", _async_handler)]

        yarn = AsyncYarn()
        res = execute_direct(yarn, "async_tool", {"val": "123"})
        self.assertEqual(res, "async_result_123")

    def test_sandbox_fail_closed_when_bwrap_missing(self):
        with patch.object(BubblewrapBuilder, "is_available", return_value=False):
            builder = create_sandbox_builder(["python", "-c", "print(1)"], writable=True)
            with self.assertRaises(SandboxUnavailableError):
                builder.run()

    def test_isolated_strand_fail_closed_when_bwrap_unavailable(self):
        mock_yarn = MagicMock()
        mock_yarn.__class__.__name__ = "MockYarn"
        mock_yarn.get_strands.return_value = [Strand(name="mock_tool", description="Mock", handler=lambda args: "ok")]

        with patch.object(BubblewrapBuilder, "is_available", return_value=False):
            res = execute_strand(
                mock_yarn,
                "mock_tool",
                {"a": 1},
                tier="MUTATE",
            )
            self.assertIn("Sandbox isolation unavailable", res)
            self.assertIn("Install 'bubblewrap'", res)

            res_async = asyncio.run(
                execute_strand_async(
                    mock_yarn,
                    "mock_tool",
                    {"a": 1},
                    tier="MUTATE",
                )
            )
            self.assertIn("Sandbox isolation unavailable", res_async)
            self.assertIn("Install 'bubblewrap'", res_async)

    def test_strand_collision_raises_error(self):
        class MockSkein:
            def initialize(self):
                pass

            def get_active_yarns(self):
                return {"y1": YarnA(), "y2": YarnB()}

        class YarnA(Yarn):
            def __init__(self):
                super().__init__(name="y1", layer=10)

            def is_available(self):
                return True

            def get_strands(self):
                return [self.build_strand("conflicting_strand", "Conflicting A", lambda args: "a")]

        class YarnB(Yarn):
            def __init__(self):
                super().__init__(name="y2", layer=50)

            def is_available(self):
                return True

            def get_strands(self):
                return [self.build_strand("conflicting_strand", "Conflicting B", lambda args: "b")]

        test_loom = Loom(registry=MockSkein())  # type: ignore
        with self.assertRaises(StrandCollisionError):
            test_loom.initialize()

    def test_totp_code_hidden_from_llm_string_output(self):
        err = OTPChallengeRequiredError(strand_name="hyprland_exit_session")
        err_str = str(err)
        self.assertIn("2FA Confirmation Required", err_str)
        self.assertIn("hyprland_exit_session", err_str)

    def test_loom_execute_sync_handler_thread_offload(self):
        main_thread_ident = threading.get_ident()
        handler_thread_ident = None

        def sync_blocking_handler(args: dict[str, Any]) -> str:
            nonlocal handler_thread_ident
            handler_thread_ident = threading.get_ident()
            return f"sync_done_{args.get('x', '')}"

        test_loom = Loom()
        test_loom.strands["sync_strand"] = Strand(
            name="sync_strand", description="Sync", tier="observe", handler=sync_blocking_handler
        )
        test_loom._strand_to_yarn["sync_strand"] = MagicMock()
        test_loom._initialized = True

        res = asyncio.run(test_loom.execute("sync_strand", {"x": "ok"}))
        self.assertEqual(res, "sync_done_ok")
        self.assertIsNotNone(handler_thread_ident)
        self.assertNotEqual(handler_thread_ident, main_thread_ident)


if __name__ == "__main__":
    unittest.main()
