"""
Textile Security Context & Visual OTP Verification Manager.
Provides thread-safe and multi-process SQLite-backed single-use visual challenge OTP verification.
"""

import contextlib
import hashlib
import secrets
import shutil
import sqlite3
import subprocess
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from textile.core.telemetry.database import TapestryDatabase


def _display_visual_otp_osd(otp: str, strand_name: str) -> None:
    """Display single-use Visual OTP code on screen for human verification."""
    notify_bin = shutil.which("notify-send")
    if notify_bin:
        with contextlib.suppress(OSError, subprocess.SubprocessError):
            subprocess.Popen(
                [
                    notify_bin,
                    "-u",
                    "critical",
                    "-t",
                    "30000",
                    "-a",
                    "Textile",
                    f"Textile Code: {otp}",
                    f"Strand: {strand_name}",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )


@dataclass(slots=True)
class PendingOTP:
    """A single-use 4-digit challenge OTP bound to an exact strand execution."""

    challenge_id: str
    otp: str
    strand_name: str
    args_hash: str
    created_at: float = field(default_factory=time.time)
    ttl_seconds: float = 30.0
    failed_attempts: int = 0
    max_attempts: int = 3

    def is_valid(self, now: float | None = None) -> bool:
        current_time = now if now is not None else time.time()
        return (
            self.failed_attempts < self.max_attempts
            and (current_time - self.created_at) <= self.ttl_seconds
        )


class OTPManager:
    """Manages thread-safe, multi-process, single-use visual challenge OTPs backed by SQLite."""

    def __init__(self, database: TapestryDatabase | None = None) -> None:
        self._database = database or TapestryDatabase(persist=True)
        self._lock = threading.Lock()

    def _purge_expired(self, connection: sqlite3.Connection, now: float) -> None:
        connection.execute("DELETE FROM otp_challenges WHERE (created_at + ttl_seconds) < ?", (now,))

    def create_challenge(self, strand_name: str, args_hash: str) -> str:
        """Generates or retrieves an active 4-digit OTP bound to a specific strand call and args hash."""
        now = time.time()
        with self._lock, self._database._lock, self._database.get_connection() as conn:
            self._purge_expired(conn, now)

            # Check if active unexpired challenge exists for this exact strand and args
            cursor = conn.cursor()
            query_select = (
                "SELECT otp FROM otp_challenges "
                "WHERE strand_name = ? AND args_hash = ? AND (created_at + ttl_seconds) >= ?"
            )
            cursor.execute(query_select, (strand_name, args_hash, now))
            if row := cursor.fetchone():
                return str(row[0])

            # Generate collision-free 4-digit OTP
            while True:
                otp = f"{secrets.randbelow(10000):04d}"
                cid = secrets.token_hex(16)
                try:
                    conn.execute(
                        """
                        INSERT INTO otp_challenges (
                            challenge_id, otp, strand_name, args_hash,
                            created_at, ttl_seconds, failed_attempts, max_attempts
                        )
                        VALUES (?, ?, ?, ?, ?, ?, 0, 3)
                        """,
                        (cid, otp, strand_name, args_hash, now, 30.0),
                    )
                    return otp
                except sqlite3.IntegrityError:
                    continue

    def verify_and_consume(self, otp: str, strand_name: str, _args_hash: str = "") -> bool:
        """Validates and INSTANTLY consumes the OTP atomically so it can never be reused."""
        now = time.time()
        with self._lock, self._database._lock, self._database.get_connection() as conn:
            self._purge_expired(conn, now)

            cursor = conn.cursor()
            cursor.execute(
                "SELECT challenge_id, strand_name, failed_attempts, max_attempts FROM otp_challenges WHERE otp = ?",
                (otp.strip(),),
            )
            row = cursor.fetchone()
            if not row:
                return False

            cid, bound_strand, failed_attempts, max_attempts = row[0], row[1], row[2], row[3]
            if bound_strand == strand_name:
                # Atomically consume
                conn.execute("DELETE FROM otp_challenges WHERE challenge_id = ?", (cid,))
                return True

            # Mismatched strand: increment failed attempts
            if failed_attempts + 1 >= max_attempts:
                conn.execute("DELETE FROM otp_challenges WHERE challenge_id = ?", (cid,))
            else:
                conn.execute(
                    "UPDATE otp_challenges SET failed_attempts = failed_attempts + 1 WHERE challenge_id = ?",
                    (cid,),
                )
            return False

    def clear(self) -> None:
        with self._lock, self._database._lock, self._database.get_connection() as conn:
            conn.execute("DELETE FROM otp_challenges")


global_otp_manager = OTPManager()


class PolicyViolationError(PermissionError):
    """Raised when an operation violates security policy (e.g. invalid/expired OTP)."""


class OTPChallengeRequiredError(PermissionError):
    """Raised when a MUTATE, PRIVILEGED, or SYSTEM_EXEC strand requires visual OTP confirmation."""

    def __init__(self, otp: str, strand_name: str, args_hash: str) -> None:
        self.otp = otp
        self.strand_name = strand_name
        self.args_hash = args_hash
        # CRITICAL: Do NOT leak self.otp in string representation returned to LLM tool context!
        super().__init__(
            f"OTP Confirmation Required for '{strand_name}'. "
            f"A single-use 4-digit verification code has been displayed on the user's screen. "
            f"Ask the user to read the 4-digit code off their screen and confirm by passing otp='<code_from_user>'."
        )


def verify_security_policy(
    tier: Any,
    strand_name: str,
    args_json: str = "",
    otp: str | None = None,
) -> bool:
    """Canonical security policy gate.

    - OBSERVE and INTERACT strands execute freely (returns False).
    - MUTATE, PRIVILEGED, and SYSTEM_EXEC strands require a single-use 4-digit OTP.
    - If OTP is missing/invalid, generates an OTP, displays on-screen OSD notification,
      and raises OTPChallengeRequiredError or PolicyViolationError.
    - If OTP is valid and consumed, returns True.
    """
    tier_val = tier.value if hasattr(tier, "value") else str(tier).lower()

    if tier_val in ("observe", "interact"):
        return False

    # Calculate deterministic hash of call arguments
    args_hash = hashlib.sha256(args_json.encode("utf-8")).hexdigest()

    if otp:
        if global_otp_manager.verify_and_consume(otp, strand_name, args_hash):
            return True
        raise PolicyViolationError(
            f"[Security Policy Violation - Invalid/Expired OTP] Invalid or expired OTP code for strand '{strand_name}'."
        )

    # No OTP provided: generate/fetch OTP challenge and display visually on desktop screen
    challenge_code = global_otp_manager.create_challenge(strand_name, args_hash)
    _display_visual_otp_osd(challenge_code, strand_name)
    raise OTPChallengeRequiredError(otp=challenge_code, strand_name=strand_name, args_hash=args_hash)
