"""
Textile Core Layer 1 - Security & OTP Engine Unit Tests.
Verifies single-use OTP generation, consumption, action-binding, and policy enforcement.
"""

import hashlib
import json
import pytest

from textile import CapabilityTier
from textile.core.security.context import (
    OTPChallengeRequiredError,
    OTPManager,
    PolicyViolationError,
    global_otp_manager,
    verify_security_policy,
)


class TestOTPManager:
    def test_create_and_consume_otp(self):
        mgr = OTPManager()
        strand = "file_op"
        args_hash = hashlib.sha256(b'{"op": "delete"}').hexdigest()

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
        mgr = OTPManager()
        strand = "packagekit_install"
        args_hash = hashlib.sha256(b'{"pkg": "git"}').hexdigest()

        otp1 = mgr.create_challenge(strand, args_hash)
        otp2 = mgr.create_challenge(strand, args_hash)
        assert otp1 == otp2


class TestSecurityPolicyGate:
    def setup_method(self):
        global_otp_manager.clear()

    def test_observe_tier_allows_without_otp(self):
        # OBSERVE tier executes freely
        verify_security_policy(CapabilityTier.OBSERVE, "sensors_get_telemetry")

    def test_mutate_tier_requires_otp_challenge(self):
        strand = "file_op"
        args_json = json.dumps({"op": "write", "path": "/tmp/test.txt"})
        args_hash = hashlib.sha256(args_json.encode("utf-8")).hexdigest()

        # Without OTP, raises OTPChallengeRequiredError
        with pytest.raises(OTPChallengeRequiredError) as exc_info:
            verify_security_policy(CapabilityTier.MUTATE, strand, args_json=args_json)

        err = exc_info.value
        assert err.strand_name == strand
        assert err.args_hash == args_hash
        assert len(err.otp) == 4

        # With correct OTP, passes cleanly
        verify_security_policy(CapabilityTier.MUTATE, strand, args_json=args_json, otp=err.otp)

        # Replaying the same OTP fails
        with pytest.raises(PolicyViolationError):
            verify_security_policy(CapabilityTier.MUTATE, strand, args_json=args_json, otp=err.otp)

    def test_privileged_and_system_exec_require_otp(self):
        strand = "polkit_pkexec"
        args_json = json.dumps({"cmd": "systemctl restart bluetooth"})

        with pytest.raises(OTPChallengeRequiredError) as exc_info:
            verify_security_policy(CapabilityTier.PRIVILEGED, strand, args_json=args_json)

        otp = exc_info.value.otp
        verify_security_policy(CapabilityTier.PRIVILEGED, strand, args_json=args_json, otp=otp)
