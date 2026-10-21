"""
Textile Core Layer 1 - Security & 2FA TOTP Engine Unit Tests.
Verifies RFC 6238 TOTP verification, single-use replay prevention, and policy enforcement.
"""

import time
from datetime import UTC, datetime
from typing import Any

import pyotp
import pytest

from textile import Strand, Yarn
from textile.core.loom.context import (
    OTPManager,
    check_security_policy,
    get_totp_secret,
    get_totp_uri,
    global_otp_manager,
)
from textile.core.loom.mesh import loom
from textile.core.skein.mesh import skein


class TestOTPManager:
    def test_totp_verification_success_and_replay_rejection(self):
        secret = pyotp.random_base32()
        mgr = OTPManager(secret=secret)
        totp = pyotp.TOTP(secret)
        code = totp.now()

        # Valid TOTP code succeeds
        assert mgr.verify_and_consume(code) is True

        # Replay attack in same window fails immediately
        assert mgr.verify_and_consume(code) is False

    def test_totp_wrong_code_fails(self):
        secret = pyotp.random_base32()
        mgr = OTPManager(secret=secret)
        assert mgr.verify_and_consume("000000") is False

    def test_totp_secret_generation_and_uri(self):
        secret = get_totp_secret()
        assert len(secret) >= 16
        uri = get_totp_uri(secret)
        assert uri.startswith("otpauth://totp/Textile")
        assert f"secret={secret}" in uri


class MockElevatedYarn(Yarn):
    def __init__(self):
        super().__init__(name="mock_elevated", layer=10, description="Mock Yarn")

    def is_available(self) -> bool:
        return True

    def get_strands(self) -> list[Strand]:
        async def _dummy_install(args: Any):
            pkg = args.get("packages") if isinstance(args, dict) else args
            return f"Error: Package '{pkg}' failed to install."

        return [
            Strand(
                name="mock_privileged_install",
                description="Mock install",
                tier="privileged",
                parameters={"packages": {"type": "string", "description": "Package name"}},
                handler=_dummy_install,
                raw_handler=_dummy_install,
            )
        ]


class MockValidatedYarn(Yarn):
    def __init__(self):
        super().__init__(name="mock_val_yarn", layer=10, description="Mock Val Yarn")

    def is_available(self) -> bool:
        return True

    def get_strands(self) -> list[Strand]:
        async def _dummy_fn(args: Any):
            return "Success"

        return [
            Strand(
                name="mock_strict_strand",
                description="Mock strict strand",
                tier="mutate",
                parameters={"target": {"type": "string", "description": "Target path"}},
                required=["target"],
                handler=_dummy_fn,
                raw_handler=_dummy_fn,
            )
        ]


class TestSecurityPolicyGate:
    def setup_method(self):
        global_otp_manager.clear()

    def test_observe_tier_allows_without_otp(self):
        passed, err = check_security_policy("observe", "sensors_get_telemetry")
        assert passed is True
        assert err is None

    def test_mutate_tier_requires_2fa(self):
        strand = "file_op"
        secret = global_otp_manager._get_secret()
        totp = pyotp.TOTP(secret)
        code = totp.now()

        # Without 2FA code, returns False with notice message
        passed, err = check_security_policy("mutate", strand)
        assert passed is False
        assert "2FA Confirmation Required" in str(err)

        # With correct 2FA code, passes cleanly
        passed_ok, err_ok = check_security_policy("mutate", strand, otp=code)
        assert passed_ok is True
        assert err_ok is None

        # Replaying the same code fails
        passed_replay, err_replay = check_security_policy("mutate", strand, otp=code)
        assert passed_replay is False
        assert "Invalid or expired 2FA code" in str(err_replay)

    def test_otp_drift_and_monotonic_replay_protection(self):
        secret = global_otp_manager._get_secret()
        totp = pyotp.TOTP(secret)

        now = time.time()
        base_step = int(now / 30)

        # Code from current timestep
        curr_time = datetime.fromtimestamp(base_step * 30, tz=UTC)
        curr_code = totp.at(curr_time)

        # First verification succeeds
        assert global_otp_manager.verify_and_consume(curr_code) is True

        # Immediate replay of same code fails
        assert global_otp_manager.verify_and_consume(curr_code) is False

        # Attempting past window (-1) after consuming current window fails monotonically
        past_time = datetime.fromtimestamp((base_step - 1) * 30, tz=UTC)
        past_code = past_time and totp.at(past_time)
        assert global_otp_manager.verify_and_consume(past_code) is False

    def test_privileged_and_system_exec_require_2fa(self):
        strand = "polkit_pkexec"
        secret = global_otp_manager._get_secret()
        totp = pyotp.TOTP(secret)
        code = totp.now()

        passed, err = check_security_policy("privileged", strand)
        assert passed is False
        assert "2FA Confirmation Required" in str(err)

        passed_ok, _ = check_security_policy("privileged", strand, otp=code)
        assert passed_ok is True

    @pytest.mark.asyncio
    async def test_loom_unmasked_error_propagation(self):
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
        mock_yarn = MockValidatedYarn()
        skein.register_yarn(mock_yarn)
        loom.initialize()
        loom._rebuild_active()

        # Missing required parameter: rejected immediately with error BEFORE 2FA check
        res_missing = await loom.execute("mock_strict_strand", {})
        assert "Error: Validation Hint" in res_missing
        assert "target" in res_missing
