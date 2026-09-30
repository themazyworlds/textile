"""
Textile Loom - High-Performance Strand Execution, Capability Resolution, and Dispatch Engine.
"""

import asyncio
import concurrent.futures
import contextlib
import inspect
import logging
import os
import time
import uuid
from dataclasses import dataclass
from typing import Any

from textile.core.definitions.layers import LAYER_CORE_POSIX_THRESHOLD as LAYER_BASE
from textile.core.execution.strands import Strand, Weft
from textile.core.execution.yarn import Yarn
from textile.core.orchestration.fabric import core_fabric_yarn
from textile.core.orchestration.instructions import fabric_instructions
from textile.core.orchestration.skein import Skein, skein
from textile.core.orchestration.stream import stream_engine
from textile.core.security.context import OriginToken, TaintTracker, verify_security_policy
from textile.core.telemetry.elastic import EventUrgency, elastic
from textile.core.telemetry.seams import seams
from textile.core.telemetry.tapestry import NoticeLevel, core_tapestry, sensory_tapestry

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class _ExecutionTelemetryContext:
    task_id: str
    strand_name: str
    args: dict[str, Any]
    tier_val: str
    trust_val: str
    token: OriginToken
    caller: str


class Loom:
    """Central runtime dispatch engine managing layer-tier capability overriding and execution."""

    def __init__(self, registry: Skein | None = None):
        self._skein = registry or skein
        self.active_yarns: dict[str, Yarn] = {}
        self.strands: dict[str, Strand] = {}
        self.wefts: list[Weft] = []
        self._strand_to_yarn: dict[str, Yarn] = {}
        self._capability_to_strand: dict[str, tuple[Strand, Yarn]] = {}
        self._initialized: bool = False

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
                with contextlib.suppress(AttributeError, TypeError, ValueError, KeyError, OSError, RuntimeError):
                    self._skein.all_yarns[name].on_unload()
        for name in new_yarns - old_yarns:
            with contextlib.suppress(AttributeError, TypeError, ValueError, KeyError, OSError, RuntimeError):
                new_active[name].on_load()

    def _rebuild_active(self) -> None:
        new_active = self._skein.get_active_yarns()
        new_strands: dict[str, Strand] = {}
        new_wefts: list[Weft] = []
        new_strand_map: dict[str, Yarn] = {}
        new_cap_map: dict[str, tuple[Strand, Yarn]] = {}

        # 1. Register Core Fabric native strands (Layer 0 foundation)
        for strand in core_fabric_yarn.get_strands():
            new_strands[strand.name] = strand
            new_strand_map[strand.name] = core_fabric_yarn

        # 2. Higher layer yarns override lower layers
        sorted_yarns = sorted(new_active.values(), key=lambda p: getattr(p, "layer", LAYER_BASE))
        for yarn in sorted_yarns:
            try:
                self._register_yarn_strands_and_wefts(yarn, new_strands, new_strand_map, new_cap_map, new_wefts)
            except (AttributeError, TypeError, ValueError, KeyError, OSError, RuntimeError) as e:
                logger.error(f"Error loading strands/wefts from yarn {yarn.name}: {e}")

        new_wefts.sort(key=lambda w: w.priority, reverse=True)
        self._notify_yarn_lifecycle_events(set(self.active_yarns.keys()), set(new_active.keys()), new_active)

        self.active_yarns, self.strands, self.wefts = new_active, new_strands, new_wefts
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

    def get_mcp_definitions(self) -> list[dict[str, Any]]:
        self.initialize()
        return fabric_instructions.get_mcp_definitions(self.get_all_strands())

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

    def _resolve_origin_token(self, origin_token: OriginToken | None) -> OriginToken:
        """Resolve and taint-track OriginToken for Layer 1/3 policy check."""
        if origin_token is not None:
            token = origin_token
        else:
            try:
                token = OriginToken.create_local_seat()
            except PermissionError:
                token = OriginToken.create_external_untrusted("unauthenticated_caller")

        if TaintTracker.is_tainted() and not token.tainted:
            token = token.taint(TaintTracker.get_taint() or "ambient_untrusted_data")

        return token

    def _record_execution_start(self, ctx: _ExecutionTelemetryContext) -> None:
        """Record task start telemetry in CoreTapestry and Elastic."""
        core_tapestry.record_task_start(
            ctx.task_id,
            ctx.strand_name,
            args=ctx.args,
            tier=ctx.tier_val,
            trust_level=ctx.trust_val,
            tainted=ctx.token.tainted,
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
                "trust_level": ctx.trust_val,
                "tainted": ctx.token.tainted,
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
        origin_token: OriginToken | None = None,
    ) -> str:
        """Native asynchronous strand execution with Layer 1/3 security policy enforcement."""
        self.initialize()
        resolved = self._resolve_target_strand(strand_name)
        if not resolved:
            return f"Error: Strand '{strand_name}' not found or no provider yarn is enabled."

        strand, _, handler = resolved
        token = self._resolve_origin_token(origin_token)
        verify_security_policy(token, strand.tier, strand.name)

        effective_caller = caller or os.getenv("TEXTILE_CALLER", "")
        task_id = str(uuid.uuid4())[:8]
        tier_val = strand.tier.value if hasattr(strand.tier, "value") else str(strand.tier)
        trust_val = token.trust_level.value if hasattr(token.trust_level, "value") else str(token.trust_level)

        ctx = _ExecutionTelemetryContext(
            task_id=task_id,
            strand_name=strand_name,
            args=args,
            tier_val=tier_val,
            trust_val=trust_val,
            token=token,
            caller=effective_caller,
        )
        self._record_execution_start(ctx)

        t0 = time.perf_counter()
        success = True
        err = None
        try:
            if inspect.iscoroutinefunction(handler):
                return await handler(args)
            return await asyncio.to_thread(handler, args)
        except Exception as e:
            success = False
            err = str(e)
            raise
        finally:
            dur = (time.perf_counter() - t0) * 1000.0
            self._record_execution_end(ctx, dur, success, err)

    def execute_sync(
        self,
        strand_name: str,
        args: dict[str, Any],
        *,
        caller: str | None = None,
        origin_token: OriginToken | None = None,
    ) -> str:
        """Synchronous bridge for CLI and non-async environments."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(
                    asyncio.run, self.execute(strand_name, args, caller=caller, origin_token=origin_token)
                ).result()
        return asyncio.run(self.execute(strand_name, args, caller=caller, origin_token=origin_token))

    def get_all_wefts(self) -> list[Weft]:
        """Return all active Weft attunements sorted by priority."""
        self.initialize()
        return list(self.wefts)

    def process_stream(self, chunk: str) -> str:
        """Process real-time streaming text chunk through active Weft attunements."""
        self.initialize()
        return stream_engine.process_stream(chunk, self.wefts)

    async def process_stream_async(self, chunk: str) -> str:
        """Asynchronous streaming text processor for active Wefts."""
        self.initialize()
        return await stream_engine.process_stream_async(chunk, self.wefts)

    def get_fabric_instructions(self) -> str:
        """Deliver active strand tools, weft stream attunements, and security governance to the MCP/Voice client."""
        self.initialize()
        return fabric_instructions.build_instructions(self.active_yarns)


loom = Loom()
seams.set_loom(loom)
