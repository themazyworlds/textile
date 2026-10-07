"""
Textile Loom - High-Performance Strand Execution, Capability Resolution, and Dispatch Engine.
"""

import asyncio
import concurrent.futures
import contextlib
import json
import os
import time
import uuid
from dataclasses import dataclass
from typing import Any

from textile.core.definitions.errors import SAFE_EXCEPTIONS, StrandCollisionError, StrandOperationalError
from textile.core.definitions.layers import LAYER_CORE_POSIX_THRESHOLD as LAYER_BASE
from textile.core.execution.strands import Strand, Weft
from textile.core.execution.yarn import Yarn
from textile.core.orchestration.skein import Skein, skein
from textile.core.security.context import OTPChallengeRequiredError, PolicyViolationError, verify_security_policy
from textile.core.telemetry.blackboard import NoticeLevel, sensory_tapestry
from textile.core.telemetry.elastic import EventUrgency, elastic
from textile.core.telemetry.ledger import core_tapestry
from textile.core.telemetry.log import get_logger

logger = get_logger(__name__)



@dataclass(slots=True)
class _ExecutionTelemetryContext:
    task_id: str
    strand_name: str
    args: dict[str, Any]
    tier_val: str
    caller: str


class Loom:
    """Central runtime dispatch engine managing layer-tier capability overriding and execution."""

    def __init__(self, registry: Skein | None = None):
        self._skein = registry or skein
        self.active_yarns: dict[str, Yarn] = {}
        self.strands: dict[str, Strand] = {}
        self._wefts: list[Weft] = []
        self._strand_to_yarn: dict[str, Yarn] = {}
        self._capability_to_strand: dict[str, tuple[Strand, Yarn]] = {}
        self._initialized: bool = False

    @property
    def wefts(self) -> list[Weft]:
        self.initialize()
        return self._wefts

    def get_settings(self, yarn_name: str) -> Any:
        """Retrieve validated settings model for any yarn by name."""
        self.initialize()
        if yarn_name in self.active_yarns:
            return self.active_yarns[yarn_name].settings
        return self._skein.get_yarn_settings_model(yarn_name)

    def initialize(self) -> None:
        if self._initialized:
            return
        self._skein.initialize()
        self._rebuild_active()
        self._initialized = True

    def _register_yarn_strands_and_wefts(
        self,
        yarn: Yarn,
        new_strands: dict[str, Strand],
        new_strand_map: dict[str, Yarn],
        new_cap_map: dict[str, tuple[Strand, Yarn]],
        new_wefts: list[Weft],
    ) -> None:
        """Register a single yarn's strands and wefts into Loom lookup maps."""
        for strand in yarn.get_strands():
            if strand.name in new_strands and not strand.capability:
                existing_yarn = new_strand_map[strand.name]
                if existing_yarn.name != yarn.name:
                    logger.warning(
                        "loom.strand_collision",
                        strand=strand.name,
                        existing_yarn=existing_yarn.name,
                        new_yarn=yarn.name,
                    )
                    raise StrandCollisionError(strand.name, existing_yarn.name, yarn.name)
            new_strands[strand.name] = strand
            new_strand_map[strand.name] = yarn
            if strand.capability:
                new_cap_map[strand.capability] = (strand, yarn)
        new_wefts.extend(yarn.get_wefts())

    def _notify_yarn_lifecycle_events(
        self,
        old_yarns: set[str],
        new_yarns: set[str],
        new_active: dict[str, Yarn],
    ) -> None:
        """Trigger on_unload and on_load hooks for deactivated and activated yarns."""
        for name in old_yarns - new_yarns:
            if name in self._skein.all_yarns:
                with contextlib.suppress(*SAFE_EXCEPTIONS):
                    self._skein.all_yarns[name].on_unload()
        for name in new_yarns - old_yarns:
            with contextlib.suppress(*SAFE_EXCEPTIONS):
                new_active[name].on_load()

    def _rebuild_active(self) -> None:
        new_active = self._skein.get_active_yarns()
        new_strands: dict[str, Strand] = {}
        new_wefts: list[Weft] = []
        new_strand_map: dict[str, Yarn] = {}
        new_cap_map: dict[str, tuple[Strand, Yarn]] = {}

        # Higher layer yarns override lower layers
        sorted_yarns = sorted(new_active.values(), key=lambda p: getattr(p, "layer", LAYER_BASE))
        for yarn in sorted_yarns:
            try:
                self._register_yarn_strands_and_wefts(yarn, new_strands, new_strand_map, new_cap_map, new_wefts)
            except SAFE_EXCEPTIONS as e:
                logger.error("loom.yarn_load_failed", yarn=yarn.name, error=str(e))

        new_wefts.sort(key=lambda w: w.priority, reverse=True)
        self._notify_yarn_lifecycle_events(set(self.active_yarns.keys()), set(new_active.keys()), new_active)

        self.active_yarns, self.strands, self._wefts = new_active, new_strands, new_wefts
        self._strand_to_yarn, self._capability_to_strand = new_strand_map, new_cap_map

    def get_strand_override_status(self, strand: Strand, yarn: Yarn) -> tuple[bool, str | None, str | None]:
        if strand.capability and strand.capability in self._capability_to_strand:
            _active_s, active_y = self._capability_to_strand[strand.capability]
            if active_y.name != yarn.name:
                return True, active_y.name, strand.capability
        return False, None, None

    def get_all_strands(self) -> list[Strand]:
        self.initialize()
        return [
            s
            for name, s in self.strands.items()
            if not (
                self._strand_to_yarn.get(name) and self.get_strand_override_status(s, self._strand_to_yarn[name])[0]
            )
        ]

    def get_strand(self, strand_name: str) -> Strand | None:
        self.initialize()
        return self.strands.get(strand_name)

    def _resolve_target_strand(self, strand_name: str) -> tuple[Strand, Yarn, Any] | None:
        """Resolve active strand object, providing yarn, and handler function."""
        strand = self.strands.get(strand_name)
        yarn = self._strand_to_yarn.get(strand_name)
        if not yarn or not strand or not strand.handler:
            return None

        handler = strand.handler
        if strand.capability and strand.capability in self._capability_to_strand:
            active_s, active_y = self._capability_to_strand[strand.capability]
            if active_y.name != yarn.name:
                strand, yarn = active_s, active_y
                handler = strand.handler or handler

        return strand, yarn, handler

    def _record_execution_start(self, ctx: _ExecutionTelemetryContext) -> None:
        """Record task start telemetry in CoreTapestry and Elastic."""
        core_tapestry.record_task_start(
            ctx.task_id,
            ctx.strand_name,
            args=ctx.args,
            tier=ctx.tier_val,
        )
        elastic.broadcast(
            topic="loom.tool_start",
            source="loom",
            summary=f"Starting strand '{ctx.strand_name}' [{ctx.tier_val.upper()}]",
            urgency=EventUrgency.AMBIENT,
            data={"task_id": ctx.task_id, "strand": ctx.strand_name, "caller": ctx.caller, "tier": ctx.tier_val},
        )

    def _record_execution_end(
        self,
        ctx: _ExecutionTelemetryContext,
        dur_ms: float,
        success: bool,
        err: str | None,
    ) -> None:
        """Record task completion telemetry in CoreTapestry, SensoryTapestry, and Elastic."""
        core_tapestry.record_task_end(ctx.task_id, success=success, duration_ms=dur_ms, error=err)
        msg = (
            f"Executed '{ctx.strand_name}' [{ctx.tier_val.upper()}] ({dur_ms:.1f}ms)"
            if success
            else f"Failed '{ctx.strand_name}': {err}"
        )
        sensory_tapestry.stitch(
            level=NoticeLevel.INFO if success else NoticeLevel.ERROR,
            source=ctx.strand_name,
            message=msg,
            data={
                "caller": ctx.caller,
                "args": ctx.args,
                "tier": ctx.tier_val,
            },
        )
        elastic.broadcast(
            topic="loom.tool_done",
            source="loom",
            summary=msg,
            urgency=EventUrgency.NOTICE if success else EventUrgency.ALERT,
            data={
                "task_id": ctx.task_id,
                "strand": ctx.strand_name,
                "success": success,
                "duration_ms": dur_ms,
                "caller": ctx.caller,
                "error": err,
            },
        )

    async def execute(
        self,
        strand_name: str,
        args: dict[str, Any],
        *,
        caller: str | None = None,
        otp: str | None = None,
    ) -> str:
        """Native asynchronous strand execution with Visual OTP security policy enforcement."""
        self.initialize()
        resolved = self._resolve_target_strand(strand_name)
        if not resolved:
            return f"Error: Strand '{strand_name}' not found or no provider yarn is enabled."

        strand, _, handler = resolved
        clean_args = args.copy()
        effective_otp = otp or clean_args.pop("otp", None)
        if isinstance(effective_otp, str):
            effective_otp = effective_otp.strip()

        args_json = json.dumps(clean_args, sort_keys=True)
        otp_verified = verify_security_policy(strand.tier, strand.name, args_json=args_json, otp=effective_otp)

        effective_caller = caller or os.getenv("TEXTILE_CALLER", "")
        task_id = str(uuid.uuid4())[:8]
        tier_val = strand.tier.value if hasattr(strand.tier, "value") else str(strand.tier)

        ctx = _ExecutionTelemetryContext(
            task_id=task_id,
            strand_name=strand_name,
            args=args,
            tier_val=tier_val,
            caller=effective_caller,
        )
        self._record_execution_start(ctx)

        t0 = time.perf_counter()
        success = True
        err = None
        try:
            res = await handler(args)
            if isinstance(res, str):
                lower_res = res.lower()
                error_indicators = ("error:", "installation error:", "removal error:", "failed to", "permission error:")
                if any(k in lower_res for k in error_indicators):
                    if otp_verified:
                        res = f"[OTP Code Verified & Accepted] Operational Error in strand '{strand_name}': {res}"
                    else:
                        res = f"[Operational Failure] Strand '{strand_name}' error: {res}"
            return res
        except (PolicyViolationError, OTPChallengeRequiredError):
            success = False
            err = "Security Policy Gate Failure"
            raise
        except Exception as e:
            success = False
            err = str(e)
            if otp_verified:
                raise StrandOperationalError(
                    strand_name=strand_name,
                    reason=f"[OTP Code Verified & Accepted] Operational Failure in strand '{strand_name}': {e}",
                    original_error=e,
                ) from e
            raise StrandOperationalError(
                strand_name=strand_name,
                reason=f"[Operational Failure] Strand '{strand_name}' failed during execution: {e}",
                original_error=e,
            ) from e
        finally:
            dur = (time.perf_counter() - t0) * 1000.0
            self._record_execution_end(ctx, dur, success, err)


    def execute_sync(
        self,
        strand_name: str,
        args: dict[str, Any],
        *,
        caller: str | None = None,
        otp: str | None = None,
    ) -> str:
        """Synchronous bridge for CLI and non-async environments."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(
                    asyncio.run, self.execute(strand_name, args, caller=caller, otp=otp)
                ).result()
        return asyncio.run(self.execute(strand_name, args, caller=caller, otp=otp))

    def get_all_wefts(self) -> list[Weft]:
        """Return all active Weft attunements sorted by priority."""
        self.initialize()
        return self.wefts.copy()


loom = Loom()
