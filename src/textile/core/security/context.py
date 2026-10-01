"""
Textile Core Layer 1 - Context & OTP Security Engine.
Defines dynamic Visual OTP security policy and single-use challenge verification.
"""

import hashlib
import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class PendingOTP:
    """A single-use 4-digit challenge OTP bound to an exact strand execution."""

    challenge_id: str
    otp: str
    strand_name: str
    args_hash: str
    created_at: float = field(default_factory=time.time)
    ttl_seconds: float = 30.0
    consumed: bool = False
    failed_attempts: int = 0
    max_attempts: int = 3

    def is_valid(self) -> bool:
        return (
            not self.consumed
            and self.failed_attempts < self.max_attempts
            and (time.time() - self.created_at) <= self.ttl_seconds
        )


class OTPManager:
    """Manages thread-safe, collision-free single-use visual challenge OTPs."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._pending: dict[str, PendingOTP] = {}
        self._otp_map: dict[str, str] = {}

    def _purge_expired_locked(self, now: float) -> None:
        expired_ids = [cid for cid, ch in self._pending.items() if not ch.is_valid()]
        for cid in expired_ids:
            ch = self._pending.pop(cid, None)
            if ch and self._otp_map.get(ch.otp) == cid:
                del self._otp_map[ch.otp]

    def create_challenge(self, strand_name: str, args_hash: str) -> str:
        """Generates a 4-digit OTP bound to a specific strand call and args hash."""
        with self._lock:
            now = time.time()
            self._purge_expired_locked(now)

            # Check if an active valid challenge already exists for this exact call
            for challenge in self._pending.values():
                if challenge.strand_name == strand_name and challenge.args_hash == args_hash and challenge.is_valid():
                    return challenge.otp

            # Generate collision-free OTP code and unique internal challenge ID
            while True:
                otp = f"{secrets.randbelow(10000):04d}"
                if otp not in self._otp_map:
                    break

            cid = secrets.token_hex(16)
            ch = PendingOTP(
                challenge_id=cid,
                otp=otp,
                strand_name=strand_name,
                args_hash=args_hash,
                created_at=now,
            )
            self._pending[cid] = ch
            self._otp_map[otp] = cid
            return otp

    def verify_and_consume(self, otp: str, strand_name: str, args_hash: str) -> bool:
        """Validates and INSTANTLY consumes the OTP atomically so it can never be reused."""
        with self._lock:
            now = time.time()
            self._purge_expired_locked(now)

            cid = self._otp_map.get(otp)
            if not cid or cid not in self._pending:
                return False

            challenge = self._pending[cid]
            if not challenge.is_valid():
                self._pending.pop(cid, None)
                self._otp_map.pop(otp, None)
                return False

            if challenge.strand_name == strand_name and challenge.args_hash == args_hash:
                challenge.consumed = True
                self._pending.pop(cid, None)
                self._otp_map.pop(otp, None)
                return True

            challenge.failed_attempts += 1
            if challenge.failed_attempts >= challenge.max_attempts:
                self._pending.pop(cid, None)
                self._otp_map.pop(otp, None)
            return False

    def clear(self) -> None:
        with self._lock:
            self._pending.clear()
            self._otp_map.clear()


global_otp_manager = OTPManager()


class PolicyViolationError(PermissionError):
    """Raised when an operation violates security policy (e.g. invalid/expired OTP)."""

    pass


class OTPChallengeRequiredError(PermissionError):
    """Raised when a MUTATE, PRIVILEGED, or SYSTEM_EXEC strand requires visual OTP confirmation."""

    def __init__(self, otp: str, strand_name: str, args_hash: str) -> None:
        self.otp = otp
        self.strand_name = strand_name
        self.args_hash = args_hash
        super().__init__(
            f"OTP Confirmation Required for '{strand_name}'. "
            f"Display OTP on screen: [{otp}]. Confirm by passing otp='{otp}'."
        )


def verify_security_policy(
    tier: Any,
    strand_name: str,
    args_json: str = "",
    otp: str | None = None,
) -> None:
    """Canonical security policy gate.

    - OBSERVE and INTERACT strands execute freely.
    - MUTATE, PRIVILEGED, and SYSTEM_EXEC strands require a single-use 4-digit OTP.
    - If OTP is missing/invalid, generates an OTP and raises OTPChallengeRequiredError.
    """
    tier_val = tier.value if hasattr(tier, "value") else str(tier).lower()

    if tier_val in ("observe", "interact"):
        return

    # Calculate deterministic hash of call arguments
    args_hash = hashlib.sha256(args_json.encode("utf-8")).hexdigest()

    if otp:
        if global_otp_manager.verify_and_consume(otp, strand_name, args_hash):
            return
        raise PolicyViolationError(
            f"Security Policy Violation: Invalid or expired OTP code for strand '{strand_name}'."
        )

    # No OTP provided: generate/fetch OTP challenge
    challenge_code = global_otp_manager.create_challenge(strand_name, args_hash)
    raise OTPChallengeRequiredError(otp=challenge_code, strand_name=strand_name, args_hash=args_hash)
