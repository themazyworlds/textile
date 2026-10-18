"""
Textile Security Context & 2FA TOTP Verification Manager.
Provides RFC 6238 Time-Based One-Time Password (TOTP) verification and single-use replay protection.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

lazy import pyotp
lazy from desktop_notifier import DesktopNotifier, Urgency

from textile.core.definitions.errors import (
    OTPChallengeRequiredError,
    PolicyViolationError,
)
from textile.core.security.policy import get_tier_policy
lazy from textile.core.telemetry.database import TapestryDatabase


def _display_totp_osd(code: str, strand_name: str, reason: str | None = None) -> None:
    """Displays 2FA TOTP code on desktop screen via native D-Bus desktop-notifier."""

    async def _send() -> None:
        with contextlib.suppress(OSError, RuntimeError):
            notifier = DesktopNotifier(app_name="Textile")
            msg = f"Strand: {strand_name}\nReason: {reason}" if reason else f"Strand: {strand_name}"
            await notifier.send(
                title=f"Textile 2FA: {code}",
                message=msg,
                urgency=Urgency.Critical,
                timeout=30,
            )

    try:
        asyncio.get_running_loop()
        thread = threading.Thread(target=lambda: asyncio.run(_send()))
        thread.start()
        thread.join(timeout=1.0)
    except RuntimeError:
        with contextlib.suppress(OSError, RuntimeError):
            asyncio.run(_send())


def get_totp_secret() -> str:
    """Retrieves or creates the local base32 TOTP secret for RFC 6238 authentication."""
    if env_secret := os.getenv("TEXTILE_TOTP_SECRET"):
        return env_secret.strip()

    secret_file = Path.home() / ".config" / "textile" / "totp.secret"
    if secret_file.exists():
        try:
            content = secret_file.read_text(encoding="utf-8").strip()
            if content:
                return content
        except OSError:
            pass

    new_secret = pyotp.random_base32()
    try:
        secret_file.parent.mkdir(parents=True, exist_ok=True)
        secret_file.write_text(new_secret, encoding="utf-8")
        secret_file.chmod(0o600)
    except OSError:
        pass
    return new_secret


def get_totp_uri(secret: str | None = None) -> str:
    """Generates standard otpauth:// provisioning URI for authenticator apps."""
    sec = secret or get_totp_secret()
    return pyotp.totp.TOTP(sec).provisioning_uri(name="Textile Desktop", issuer_name="Textile")


class OTPManager:
    """Manages thread-safe, multi-process RFC 6238 TOTP verification and replay protection."""

    def __init__(self, database: TapestryDatabase | None = None, secret: str | None = None) -> None:
        self._database = database
        self._lock = threading.Lock()
        self._secret = secret

    @property
    def database(self) -> TapestryDatabase:
        if self._database is None:
            self._database = TapestryDatabase(persist=True)
        return self._database

    def _get_secret(self) -> str:
        return self._secret or get_totp_secret()

    def verify_and_consume(self, otp: str) -> bool:
        """Validates 6-digit TOTP code against local secret, preventing token replays across drift windows."""
        clean_code = otp.strip()
        if not clean_code:
            return False

        totp = pyotp.TOTP(self._get_secret())
        now = time.time()
        base_step = int(now / 30)

        for window in (0, 1, -1):
            step = base_step + window
            step_time = datetime.fromtimestamp(step * 30, tz=UTC)
            if totp.verify(clean_code, for_time=step_time):
                db = self.database
                with self._lock, db._lock, db.get_connection() as conn:
                    cursor = conn.execute("SELECT val_int FROM otp_gate_state WHERE key = 'last_used_timestep'")
                    row = cursor.fetchone()
                    if row and int(row[0]) >= step:
                        continue

                    conn.execute(
                        "INSERT INTO otp_gate_state (key, val_int, updated_at) VALUES ('last_used_timestep', ?, ?) "
                        "ON CONFLICT(key) DO UPDATE SET val_int = excluded.val_int, updated_at = excluded.updated_at",
                        (step, now),
                    )
                    return True

        return False

    def clear(self) -> None:
        db = self.database
        with self._lock, db._lock, db.get_connection() as conn:
            conn.execute("DELETE FROM otp_gate_state")


global_otp_manager = OTPManager()


def verify_security_policy(
    tier: Any,
    strand_name: str,
    otp: str | None = None,
    reason: str | None = None,
) -> bool:
    """Canonical security policy gate for 2FA TOTP."""
    policy = get_tier_policy(tier)
    if not policy.requires_2fa:
        return False

    if otp:
        if global_otp_manager.verify_and_consume(otp):
            return True
        raise PolicyViolationError(
            f"[Security Policy Violation - Invalid 2FA Code] Invalid or expired 2FA code for strand '{strand_name}'."
        )

    code = pyotp.TOTP(global_otp_manager._get_secret()).now()
    _display_totp_osd(code, strand_name, reason=reason)
    raise OTPChallengeRequiredError(strand_name=strand_name)
