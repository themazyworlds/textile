"""
Unit tests for Textile core architecture hardening.
"""

import asyncio
import unittest
from unittest.mock import patch

from textile.core.definitions.errors import SandboxUnavailableError, StrandCollisionError
from textile.core.execution.invoker import execute_direct
from textile.core.execution.yarn import Yarn
from textile.core.orchestration.loom import Loom
from textile.core.security.context import OTPManager
from textile.core.security.sandbox import BubblewrapSandbox


class TestArchitectureHardening(unittest.TestCase):
    def test_otp_manager_thread_safety_and_collision_prevention(self):
        manager = OTPManager()
        # Generate 10 challenges for different calls
        codes = set()
        for i in range(10):
            code = manager.create_challenge(f"strand_{i}", f"hash_{i}")
            self.assertEqual(len(code), 4)
            codes.add(code)

        # Ensure all generated active OTP codes are unique (no collisions)
        self.assertEqual(len(codes), 10)

        # Verification with wrong strand or wrong hash increments failed attempts
        first_code = list(codes)[0]
        self.assertFalse(manager.verify_and_consume(first_code, "wrong_strand", "wrong_hash"))
        self.assertFalse(manager.verify_and_consume(first_code, "wrong_strand", "wrong_hash"))

        # 3rd failed attempt invalidates the challenge
        self.assertFalse(manager.verify_and_consume(first_code, "wrong_strand", "wrong_hash"))
        # Subsequent attempt even with correct params must fail because max_attempts exceeded
        self.assertFalse(manager.verify_and_consume(first_code, "strand_0", "hash_0"))

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

    def test_otp_code_hidden_from_llm_string_output(self):
        from textile.core.security.context import OTPChallengeRequiredError

        err = OTPChallengeRequiredError(otp="3599", strand_name="hyprland_exit_session", args_hash="hash123")
        err_str = str(err)

        # Ensure the OTP code '3599' is NOT leaked in the error text returned to the LLM
        self.assertNotIn("3599", err_str)
        self.assertIn("A single-use 4-digit verification code has been displayed on the user's screen", err_str)


if __name__ == "__main__":
    unittest.main()
