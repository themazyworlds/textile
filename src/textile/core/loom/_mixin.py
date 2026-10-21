"""
Textile Loom Coordinator Mixin, Signals & Handlers.
Unifies strand resolution, execution, and security governance.
"""

from typing import Any
lazy import asyncio

lazy import blinker

lazy from textile.core.bus import bus, request_async
lazy from textile.core.loom.context import (
    check_security_policy,
    get_totp_secret,
    get_totp_uri,
    global_otp_manager,
)
lazy from textile.core.loom.mesh import loom
lazy from textile.core.loom.policy import get_tier_policy


class LoomMixin:
    """Mixin providing strand execution and security gating for Camshaft."""

    class LoomSignals:
        strand_execute_input: blinker.Signal = bus.signal("strand:execute_input")
        strand_execution_started: blinker.Signal = bus.signal("strand:execution_started")
        strand_executed: blinker.Signal = bus.signal("strand:executed")

    @staticmethod
    async def execute_strand(
        name: str,
        args: dict[str, Any],
        *,
        caller: str | None = None,
        otp: str | None = None,
    ) -> str:
        """Execute a strand asynchronously through the engine bus."""
        return await request_async(
            LoomMixin.LoomSignals.strand_execute_input,
            name=name,
            args=args,
            caller=caller,
            otp=otp,
        )

    @staticmethod
    def execute_strand_sync(
        name: str,
        args: dict[str, Any],
        *,
        caller: str | None = None,
        otp: str | None = None,
    ) -> str:
        """Execute a strand synchronously through the engine bus."""
        return asyncio.run(
            request_async(
                LoomMixin.LoomSignals.strand_execute_input,
                name=name,
                args=args,
                caller=caller,
                otp=otp,
            )
        )

    @staticmethod
    def get_strand(strand_name: str) -> Any:
        """Resolve a strand definition by name directly from Loom."""
        return loom.get_strand(strand_name)

    @staticmethod
    def get_all_strands() -> list[Any]:
        """Retrieve all active strands across the fabric directly from Loom."""
        return loom.get_all_strands()

    @staticmethod
    def get_yarn_for_strand(strand_name: str) -> Any:
        """Retrieve the providing Yarn instance directly from Loom."""
        return loom.get_yarn_for_strand(strand_name)

    @staticmethod
    def emit_execution_started(
        task_id: str,
        strand_name: str,
        args: dict[str, Any],
        tier_val: str,
        caller: str,
    ) -> None:
        """Emit execution started lifecycle signal."""
        LoomMixin.LoomSignals.strand_execution_started.send(
            "camshaft",
            task_id=task_id,
            strand_name=strand_name,
            args=args,
            tier_val=tier_val,
            caller=caller,
        )

    @staticmethod
    def emit_execution_completed(
        task_id: str,
        strand_name: str,
        *,
        duration_ms: float,
        success: bool,
        **kwargs: Any,
    ) -> None:
        """Emit execution completed lifecycle signal."""
        LoomMixin.LoomSignals.strand_executed.send(
            "camshaft",
            task_id=task_id,
            strand_name=strand_name,
            duration_ms=duration_ms,
            success=success,
            **kwargs,
        )

    @staticmethod
    def get_tier_policy(tier: Any) -> Any:
        """Retrieve the TierPolicy directly from policy matrix."""
        return get_tier_policy(tier)

    @staticmethod
    def check_security_policy(
        tier: Any,
        strand_name: str,
        *,
        otp: str | None = None,
        reason: str | None = None,
    ) -> tuple[bool, str | None]:
        """Verify 2FA TOTP and authorization requirements directly."""
        return check_security_policy(tier, strand_name, otp=otp, reason=reason)

    @staticmethod
    def get_totp_secret() -> str:
        """Retrieve persistent 2FA base32 secret directly."""
        return get_totp_secret()

    @staticmethod
    def get_totp_uri(secret: str | None = None) -> str:
        """Generate otpauth:// URI directly."""
        return get_totp_uri(secret=secret)

    @staticmethod
    def clear_totp() -> None:
        """Clear TOTP replay protection state directly."""
        global_otp_manager.clear()


__all__ = ["LoomMixin"]
