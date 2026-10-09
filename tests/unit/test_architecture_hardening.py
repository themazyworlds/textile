import asyncio
import unittest
from unittest.mock import MagicMock, patch

import pyotp

from textile.core.definitions.errors import SandboxUnavailableError, StrandCollisionError
from textile.core.execution.invoker import execute_direct
from textile.core.execution.isolated_runner import execute_isolated_strand
from textile.core.execution.strands import Strand
from textile.core.execution.yarn import Yarn
from textile.core.orchestration.loom import Loom
from textile.core.security.context import OTPChallengeRequiredError, OTPManager
from textile.core.security.sandbox import BubblewrapSandbox


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
                async def _async_handler(val: str) -> str:
                    await asyncio.sleep(0.001)
                    return f"async_result_{val}"

                return [self.build_strand("async_tool", "Async tool", _async_handler)]

        yarn = AsyncYarn()
        res = execute_direct(yarn, "async_tool", {"val": "123"})
        self.assertEqual(res, "async_result_123")

    def test_sandbox_fail_closed_when_bwrap_missing(self):
        with patch("shutil.which", return_value=None), self.assertRaises(SandboxUnavailableError):
            BubblewrapSandbox.wrap_command(["python", "-c", "print(1)"], tier="MUTATE")

    def test_isolated_strand_fail_closed_when_bwrap_unavailable(self):
        mock_yarn = MagicMock()
        mock_yarn.__class__.__name__ = "MockYarn"
        mock_yarn.get_strands.return_value = [
            Strand(name="mock_tool", description="Mock", handler=lambda args: "ok")
        ]

        with patch.object(BubblewrapSandbox, "is_available", return_value=False):
            res = execute_isolated_strand(
                mock_yarn,
                "mock_tool",
                {"a": 1},
                tier="MUTATE",
            )
            self.assertIn("Sandbox isolation unavailable", res)
            self.assertIn("Sandboxed strands require bubblewrap", res)

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


if __name__ == "__main__":
    unittest.main()
