"""
Textile Security Context & Visual OTP Verification Manager.
Provides thread-safe and multi-process SQLite-backed single-use visual challenge OTP verification.
"""

import contextlib
import hashlib
import html
import secrets
import shutil
import sqlite3
import subprocess
import threading
import time
from dataclasses import dataclass, field
from typing import Any

import orjson

from textile.core.telemetry.database import TapestryDatabase

MAX_SUMMARY_KEYS = 6
MAX_KEY_CHARS = 20
MAX_VALUE_CHARS = 40
VALUE_HEAD_CHARS = 18
VALUE_TAIL_CHARS = 18
MAX_GLOBAL_FAILED_OTP_GUESSES = 3
BASE_LOCKOUT_SECONDS = 60.0
FAILURE_DECAY_SECONDS = 60.0
CONSECUTIVE_WIPE_WINDOW = 600.0


def hash_args(args: Any) -> str:
    """Computes a canonical, deterministic SHA-256 hash of strand arguments."""
    if isinstance(args, str):
        try:
            parsed = orjson.loads(args)
            if isinstance(parsed, dict):
                clean = {k: v for k, v in parsed.items() if k != "otp"}
                payload = orjson.dumps(clean, option=orjson.OPT_SORT_KEYS)
            else:
                payload = orjson.dumps(parsed, option=orjson.OPT_SORT_KEYS)
        except (orjson.JSONDecodeError, TypeError):
            payload = args.encode("utf-8")
    elif isinstance(args, dict):
        clean = {k: v for k, v in args.items() if k != "otp"}
        payload = orjson.dumps(clean, option=orjson.OPT_SORT_KEYS)
    elif args is None:
        payload = b"{}"
    else:
        payload = orjson.dumps(args, option=orjson.OPT_SORT_KEYS)
    return hashlib.sha256(payload).hexdigest()


def _truncate_middle(val_str: str, max_len: int = MAX_VALUE_CHARS) -> str:
    """Truncates long strings in the middle so start and end context are both preserved."""
    if len(val_str) <= max_len:
        return val_str
    return f"{val_str[:VALUE_HEAD_CHARS]}...{val_str[-VALUE_TAIL_CHARS:]}"


def _sanitize_key(key: Any) -> str:
    """Sanitizes argument key to prevent injection, line breaking, or markup abuse."""
    k_escaped = repr(str(key))[1:-1] if isinstance(key, str) else repr(key)
    if len(k_escaped) > MAX_KEY_CHARS:
        k_escaped = f"{k_escaped[:MAX_KEY_CHARS]}..."
    return html.escape(k_escaped)


def _sanitize_value(val: Any) -> str:
    """Sanitizes argument value to prevent raw string markup or newline injection."""
    v_repr = repr(val)
    v_trunc = _truncate_middle(v_repr)
    return html.escape(v_trunc)


def _format_args_summary(args: Any) -> str:
    """Format short, secure summary of arguments for human visual verification on OSD.

    - Escapes all keys and values via repr() and html.escape() to prevent markup/injection.
    - Limits key length to MAX_KEY_CHARS.
    - Limits number of visible keys to MAX_SUMMARY_KEYS, adding (+N more) if exceeded.
    - Middle-truncates long values so key details are preserved safely.
    """
    if not args:
        return ""
    try:
        if isinstance(args, str):
            data = orjson.loads(args)
        elif isinstance(args, dict):
            data = args
        else:
            return _sanitize_value(args)

        if isinstance(data, dict):
            items: list[str] = []
            filtered_keys = [k for k in data if k != "otp"]
            display_keys = filtered_keys[:MAX_SUMMARY_KEYS]
            remaining_count = len(filtered_keys) - len(display_keys)

            for k in display_keys:
                items.append(f"{_sanitize_key(k)}={_sanitize_value(data[k])}")

            res = ", ".join(items)
            if remaining_count > 0:
                res += f" (+{remaining_count} more)"
            return res
        return _sanitize_value(data)
    except (orjson.JSONDecodeError, TypeError, ValueError):
        return _sanitize_value(str(args))


def _display_visual_otp_osd(otp: str, strand_name: str, args_summary: str = "") -> None:
    """Display single-use Visual OTP code on screen for human verification."""
    notify_bin = shutil.which("notify-send")
    if notify_bin:
        body = f"Strand: {strand_name}"
        if args_summary:
            body += f"\nArgs: {args_summary}"
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
                    body,
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


class PolicyViolationError(PermissionError):
    """Raised when an operation violates security policy (e.g. invalid/expired OTP or lockout active)."""


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


class OTPManager:
    """Manages thread-safe, multi-process, single-use visual challenge OTPs backed by SQLite."""

    def __init__(self, database: TapestryDatabase | None = None) -> None:
        self._database = database or TapestryDatabase(persist=True)
        self._lock = threading.Lock()

    def _purge_expired(self, connection: sqlite3.Connection, now: float) -> None:
        connection.execute("DELETE FROM otp_challenges WHERE (created_at + ttl_seconds) < ?", (now,))

    def _get_lockout_remaining(self, connection: sqlite3.Connection, now: float) -> float:
        cursor = connection.cursor()
        cursor.execute("SELECT updated_at FROM otp_gate_state WHERE key = 'lockout_until'")
        row = cursor.fetchone()
        if row and float(row[0]) > now:
            return float(row[0]) - now
        return 0.0

    def _get_active_failed_guesses(self, connection: sqlite3.Connection, now: float) -> int:
        cursor = connection.cursor()
        cursor.execute("SELECT val_int, updated_at FROM otp_gate_state WHERE key = 'failed_guesses'")
        row = cursor.fetchone()
        if not row:
            return 0
        val_int, updated_at = int(row[0]), float(row[1])
        if (now - updated_at) > FAILURE_DECAY_SECONDS:
            connection.execute(
                "UPDATE otp_gate_state SET val_int = 0, updated_at = ? WHERE key = 'failed_guesses'",
                (now,),
            )
            return 0
        return val_int

    def create_challenge(self, strand_name: str, args_hash: str) -> str:
        """Generates or retrieves an active 4-digit OTP bound to a specific strand call and args hash."""
        now = time.time()
        with self._lock, self._database._lock, self._database.get_connection() as conn:
            self._purge_expired(conn, now)

            remaining_lockout = self._get_lockout_remaining(conn, now)
            if remaining_lockout > 0:
                raise PolicyViolationError(
                    f"OTP rate limit exceeded: Security lockout active for {int(remaining_lockout) + 1}s "
                    "due to repeated failed authentication attempts."
                )

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

    def verify_and_consume(self, otp: str, strand_name: str, args_hash: str) -> bool:
        """Validates and INSTANTLY consumes the OTP atomically so it can never be reused.

        Counts every failed attempt globally across all OTP challenges. After 3 misses globally,
        all pending challenges are immediately wiped and an exponential backoff lockout is enforced.
        """
        now = time.time()
        with self._lock, self._database._lock, self._database.get_connection() as conn:
            self._purge_expired(conn, now)

            # Rejections enforced during active lockout
            if self._get_lockout_remaining(conn, now) > 0:
                return False

            cursor = conn.cursor()
            cursor.execute(
                "SELECT challenge_id, strand_name, args_hash FROM otp_challenges WHERE otp = ?",
                (otp.strip(),),
            )
            row = cursor.fetchone()
            if row:
                cid, bound_strand, bound_args_hash = str(row[0]), str(row[1]), str(row[2])
                if bound_strand == strand_name and bound_args_hash == args_hash:
                    # Atomically consume challenge and reset failure / lockout counters
                    conn.execute("DELETE FROM otp_challenges WHERE challenge_id = ?", (cid,))
                    conn.execute(
                        "INSERT INTO otp_gate_state (key, val_int, updated_at) VALUES ('failed_guesses', 0, ?) "
                        "ON CONFLICT(key) DO UPDATE SET val_int = 0, updated_at = ?",
                        (now, now),
                    )
                    conn.execute(
                        "INSERT INTO otp_gate_state (key, val_int, updated_at) VALUES ('consecutive_wipes', 0, ?) "
                        "ON CONFLICT(key) DO UPDATE SET val_int = 0, updated_at = ?",
                        (now, now),
                    )
                    return True

            # Any failure (invalid OTP, strand mismatch, or args_hash mismatch):
            active_failures = self._get_active_failed_guesses(conn, now)
            new_failures = active_failures + 1

            conn.execute(
                "INSERT INTO otp_gate_state (key, val_int, updated_at) VALUES ('failed_guesses', ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET val_int = ?, updated_at = ?",
                (new_failures, now, new_failures, now),
            )

            if new_failures >= MAX_GLOBAL_FAILED_OTP_GUESSES:
                # 3-miss threshold reached: wipe all pending challenges
                conn.execute("DELETE FROM otp_challenges")
                conn.execute(
                    "UPDATE otp_gate_state SET val_int = 0, updated_at = ? WHERE key = 'failed_guesses'",
                    (now,),
                )

                # Determine consecutive wipe count for exponential backoff
                cursor.execute(
                    "SELECT val_int, updated_at FROM otp_gate_state WHERE key = 'consecutive_wipes'"
                )
                w_row = cursor.fetchone()
                prev_wipes = 0
                if w_row:
                    w_count, w_time = int(w_row[0]), float(w_row[1])
                    if (now - w_time) < CONSECUTIVE_WIPE_WINDOW:
                        prev_wipes = w_count

                consecutive_wipes = prev_wipes + 1
                lockout_duration = BASE_LOCKOUT_SECONDS * (2 ** (consecutive_wipes - 1))
                lockout_until = now + lockout_duration

                conn.execute(
                    "INSERT INTO otp_gate_state (key, val_int, updated_at) VALUES ('consecutive_wipes', ?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET val_int = ?, updated_at = ?",
                    (consecutive_wipes, now, consecutive_wipes, now),
                )
                conn.execute(
                    "INSERT INTO otp_gate_state (key, val_int, updated_at) VALUES ('lockout_until', 0, ?) "
                    "ON CONFLICT(key) DO UPDATE SET updated_at = ?",
                    (lockout_until, lockout_until),
                )

            return False

    def clear(self) -> None:
        with self._lock, self._database._lock, self._database.get_connection() as conn:
            conn.execute("DELETE FROM otp_challenges")
            conn.execute("DELETE FROM otp_gate_state")


global_otp_manager = OTPManager()


def verify_security_policy(
    tier: Any,
    strand_name: str,
    args_json: str | dict[str, Any] = "",
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

    # Deterministic argument hash
    args_hash = hash_args(args_json)

    if otp:
        if global_otp_manager.verify_and_consume(otp, strand_name, args_hash):
            return True
        raise PolicyViolationError(
            f"[Security Policy Violation - Invalid/Expired OTP] Invalid or expired OTP code for strand '{strand_name}'."
        )

    # No OTP provided: generate/fetch OTP challenge (enforces lockout) and display visually on desktop screen
    challenge_code = global_otp_manager.create_challenge(strand_name, args_hash)
    args_summary = _format_args_summary(args_json)
    _display_visual_otp_osd(challenge_code, strand_name, args_summary)
    raise OTPChallengeRequiredError(otp=challenge_code, strand_name=strand_name, args_hash=args_hash)
