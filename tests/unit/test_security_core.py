"""
Textile Core Layer 1 - Security & 2FA TOTP Engine Unit Tests.
Verifies RFC 6238 TOTP verification, single-use replay prevention, and policy enforcement.
"""

from typing import Any

import pyotp
import pytest

from textile import CapabilityTier
from textile.core.security.context import (
    OTPChallengeRequiredError,
    OTPManager,
    PolicyViolationError,
    get_totp_secret,
    get_totp_uri,
    global_otp_manager,
    verify_security_policy,
)
from textile.core.telemetry.database import TapestryDatabase


class TestOTPManager:
    def test_totp_verification_success_and_replay_rejection(self):
        secret = pyotp.random_base32()
        mgr = OTPManager(database=TapestryDatabase(persist=False), secret=secret)
        totp = pyotp.TOTP(secret)
        code = totp.now()

        # Valid TOTP code succeeds
        assert mgr.verify_and_consume(code) is True

        # Replay attack in same window fails immediately
        assert mgr.verify_and_consume(code) is False

    def test_totp_wrong_code_fails(self):
        secret = pyotp.random_base32()
        mgr = OTPManager(database=TapestryDatabase(persist=False), secret=secret)
        assert mgr.verify_and_consume("000000") is False

    def test_totp_secret_generation_and_uri(self):
        secret = get_totp_secret()
        assert len(secret) >= 16
        uri = get_totp_uri(secret)
        assert uri.startswith("otpauth://totp/Textile")
        assert f"secret={secret}" in uri


class TestSecurityPolicyGate:
    def setup_method(self):
        global_otp_manager.clear()

    def test_observe_tier_allows_without_otp(self):
        # OBSERVE tier executes freely
        verify_security_policy(CapabilityTier.OBSERVE, "sensors_get_telemetry")

    def test_mutate_tier_requires_2fa(self):
        strand = "file_op"
        secret = global_otp_manager._get_secret()
        totp = pyotp.TOTP(secret)
        code = totp.now()

        # Without 2FA code, raises OTPChallengeRequiredError
        with pytest.raises(OTPChallengeRequiredError) as exc_info:
            verify_security_policy(CapabilityTier.MUTATE, strand)

        assert exc_info.value.strand_name == strand

        # With correct 2FA code, passes cleanly
        assert verify_security_policy(CapabilityTier.MUTATE, strand, otp=code) is True

        # Replaying the same code fails
        with pytest.raises(PolicyViolationError):
            verify_security_policy(CapabilityTier.MUTATE, strand, otp=code)

    def test_privileged_and_system_exec_require_2fa(self):
        strand = "polkit_pkexec"
        secret = global_otp_manager._get_secret()
        totp = pyotp.TOTP(secret)
        code = totp.now()

        with pytest.raises(OTPChallengeRequiredError):
            verify_security_policy(CapabilityTier.PRIVILEGED, strand)

        assert verify_security_policy(CapabilityTier.PRIVILEGED, strand, otp=code) is True

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
                        parameters={"packages": {"type": "string", "description": "Package name"}},
                        handler=_dummy_install,
                    )
                ]

        mock_yarn = MockElevatedYarn()
        skein.register_yarn(mock_yarn)
        loom.initialize()
        loom._rebuild_active()

        secret = global_otp_manager._get_secret()
        code = pyotp.TOTP(secret).now()

        res = await loom.execute("mock_privileged_install", {"packages": "invalid_pkg_123"}, otp=code)
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

        # Missing required parameter: rejected immediately with error BEFORE 2FA check
        res_missing = await loom.execute("mock_strict_strand", {})
        assert "Error: Validation Hint" in res_missing
        assert "target" in res_missing
