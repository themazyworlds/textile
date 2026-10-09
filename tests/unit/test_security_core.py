"""
Textile Core Layer 1 - Security & OTP Engine Unit Tests.
Verifies single-use OTP generation, consumption, action-binding, and policy enforcement.
"""

import json
from typing import Any

import pytest

from textile import CapabilityTier
from textile.core.security.context import (
    OTPChallengeRequiredError,
    OTPManager,
    PolicyViolationError,
    _format_args_summary,
    global_otp_manager,
    hash_args,
    verify_security_policy,
)
from textile.core.telemetry.database import TapestryDatabase


class TestOTPManager:
    def test_create_and_consume_otp(self):
        mgr = OTPManager(database=TapestryDatabase(persist=False))
        strand = "file_op"
        args_hash = hash_args({"op": "delete"})

        otp = mgr.create_challenge(strand, args_hash)
        assert len(otp) == 4
        assert otp.isdigit()

        # Consuming with wrong OTP fails
        assert mgr.verify_and_consume("0000", strand, args_hash) is False

        # Consuming with wrong strand fails
        assert mgr.verify_and_consume(otp, "other_strand", args_hash) is False

        # Consuming with correct OTP succeeds
        assert mgr.verify_and_consume(otp, strand, args_hash) is True

        # Replay attack: second consumption fails!
        assert mgr.verify_and_consume(otp, strand, args_hash) is False

    def test_otp_reuses_active_challenge_for_same_call(self):
        mgr = OTPManager(database=TapestryDatabase(persist=False))
        strand = "packagekit_install"
        args_hash = hash_args({"pkg": "git"})

        otp1 = mgr.create_challenge(strand, args_hash)
        otp2 = mgr.create_challenge(strand, args_hash)
        assert otp1 == otp2

    def test_hash_args_consistency(self):
        raw_dict = {"packages": "git", "force": True}
        json_str = json.dumps(raw_dict)
        h1 = hash_args(raw_dict)
        h2 = hash_args(json_str)
        # Transient otp key must not affect hash
        h3 = hash_args({"packages": "git", "force": True, "otp": "9999"})
        assert h1 == h2 == h3

    def test_format_args_summary_displays_all_keys(self):
        args = {
            "content": "A" * 120,
            "path": "/home/u/.config/textile/yarns/evil.py",
        }
        summary = _format_args_summary(args)
        assert "content=" in summary
        assert "path=&#x27;/home/u/.config/textile/yarns/evil.py&#x27;" in summary or "path='/home/u/.config/textile/yarns/evil.py'" in summary
        assert "..." in summary

    def test_format_args_summary_sanitization_and_caps(self):
        # 1. Newline and injection in keys
        args_inject = {
            "a\nStrand: fake_op": "val",
            "<b>markup</b>": "<script>alert(1)</script>",
        }
        summary_inject = _format_args_summary(args_inject)
        assert "\n" not in summary_inject
        assert "<b>" not in summary_inject
        assert "&lt;b&gt;" in summary_inject
        assert "<script>" not in summary_inject
        assert "&lt;script&gt;" in summary_inject

        # 2. Key length cap (20 chars) and key count cap (6 keys + N more)
        many_keys = {f"very_long_key_name_number_{i}": f"val_{i}" for i in range(10)}
        summary_many = _format_args_summary(many_keys)
        assert "(+4 more)" in summary_many
        # verify long keys are capped with ellipsis
        assert "..." in summary_many

    def test_three_misses_wipe_and_lockout(self):
        mgr = OTPManager(database=TapestryDatabase(persist=False))
        strand = "file_op"
        args_hash = hash_args({"path": "/tmp/test.txt"})

        otp = mgr.create_challenge(strand, args_hash)

        # 3 failed guesses
        assert mgr.verify_and_consume("0000", strand, args_hash) is False
        assert mgr.verify_and_consume("0001", strand, args_hash) is False
        assert mgr.verify_and_consume("0002", strand, args_hash) is False

        # Challenge wiped
        assert mgr.verify_and_consume(otp, strand, args_hash) is False

        # Lockout active: creating new challenges is blocked
        with pytest.raises(PolicyViolationError) as exc_info:
            mgr.create_challenge(strand, args_hash)
        assert "Security lockout active" in str(exc_info.value)

        # Unlock / clear resets lockout
        mgr.clear()
        new_otp = mgr.create_challenge(strand, args_hash)
        assert len(new_otp) == 4


class TestSecurityPolicyGate:
    def setup_method(self):
        global_otp_manager.clear()

    def test_observe_tier_allows_without_otp(self):
        # OBSERVE tier executes freely
        verify_security_policy(CapabilityTier.OBSERVE, "sensors_get_telemetry")

    def test_mutate_tier_requires_otp_challenge(self):
        strand = "file_op"
        args = {"op": "write", "path": "/tmp/test.txt"}
        args_hash = hash_args(args)

        # Without OTP, raises OTPChallengeRequiredError
        with pytest.raises(OTPChallengeRequiredError) as exc_info:
            verify_security_policy(CapabilityTier.MUTATE, strand, args_json=args)

        err = exc_info.value
        assert err.strand_name == strand
        assert err.args_hash == args_hash
        assert len(err.otp) == 4

        # With correct OTP, passes cleanly
        verify_security_policy(CapabilityTier.MUTATE, strand, args_json=args, otp=err.otp)

        # Replaying the same OTP fails
        with pytest.raises(PolicyViolationError):
            verify_security_policy(CapabilityTier.MUTATE, strand, args_json=args, otp=err.otp)

    def test_privileged_and_system_exec_require_otp(self):
        strand = "polkit_pkexec"
        args = {"cmd": "systemctl restart bluetooth"}

        with pytest.raises(OTPChallengeRequiredError) as exc_info:
            verify_security_policy(CapabilityTier.PRIVILEGED, strand, args_json=args)

        otp = exc_info.value.otp
        assert verify_security_policy(CapabilityTier.PRIVILEGED, strand, args_json=args, otp=otp) is True

    @pytest.mark.asyncio
    async def test_loom_unmasked_error_propagation(self):
        from textile import Strand, Yarn
        from textile.core.orchestration.loom import loom
        from textile.core.orchestration.skein import skein

        class MockElevatedYarn(Yarn):
            def __init__(self):
                super().__init__(name="mock_elevated", layer=10, description="Mock Yarn")

            def get_strands(self):
                async def _dummy_install(args: Any):
                    pkg = args.get("packages") if isinstance(args, dict) else args
                    return f"Error: Package '{pkg}' failed to install."

                return [
                    Strand(
                        name="mock_privileged_install",
                        description="Mock install",
                        tier=CapabilityTier.PRIVILEGED,
                        handler=_dummy_install,
                    )
                ]

        mock_yarn = MockElevatedYarn()
        skein.register_yarn(mock_yarn)
        loom.initialize()
        loom._rebuild_active()

        args = {"packages": "invalid_pkg_123"}
        args_hash = hash_args(args)
        otp = global_otp_manager.create_challenge("mock_privileged_install", args_hash)

        res = await loom.execute("mock_privileged_install", args, otp=otp)
        assert "[OTP Code Verified & Accepted]" in res
        assert "Package 'invalid_pkg_123' failed to install." in res

    @pytest.mark.asyncio
    async def test_loom_pre_otp_schema_validation(self):
        from textile import Strand, Yarn
        from textile.core.orchestration.loom import loom
        from textile.core.orchestration.skein import skein

        class MockValidatedYarn(Yarn):
            def __init__(self):
                super().__init__(name="mock_val_yarn", layer=10, description="Mock Val Yarn")

            def get_strands(self):
                async def _dummy_fn(args: Any):
                    return "Success"

                return [
                    Strand(
                        name="mock_strict_strand",
                        description="Mock strict strand",
                        tier=CapabilityTier.MUTATE,
                        parameters={"target": {"type": "string", "description": "Target path"}},
                        required=["target"],
                        handler=_dummy_fn,
                    )
                ]

        mock_yarn = MockValidatedYarn()
        skein.register_yarn(mock_yarn)
        loom.initialize()
        loom._rebuild_active()

        # Missing required parameter: rejected immediately with error BEFORE OTP gate
        res_missing = await loom.execute("mock_strict_strand", {})
        assert "Error: Validation Hint" in res_missing
        assert "target" in res_missing

