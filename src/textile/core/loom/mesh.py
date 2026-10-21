"""
Textile Loom - High-Performance Strand Execution, Capability Resolution, and Dispatch Engine.
"""

import asyncio
import contextlib
import os
import time
from pathlib import Path
from typing import Any
lazy import concurrent.futures
lazy import uuid

from needle import DEFAULT_LAYER, Yarn
from needle.errors import SAFE_EXCEPTIONS, StrandCollisionError
lazy from needle import Strand

lazy from textile.core.camshaft import camshaft
lazy from textile.core.loom.context import check_security_policy
lazy from textile.core.loom.invoker import execute_in_process
lazy from textile.core.loom.reflector import bind_strand_to_core, reflect_strands
lazy from textile.core.loom.runner import execute_strand_async
lazy from textile.core.loom.validation import validate_strand_arguments

__all__ = ["Loom", "LoomMesh", "loom", "loom_mesh"]


class Loom:
    """Central runtime dispatch engine managing layer-tier capability overriding and execution."""

    def __init__(self) -> None:
        self.active_yarns: dict[str, Yarn] = {}
        self.strands: dict[str, Strand] = {}
        self._strand_to_yarn: dict[str, Yarn] = {}
        self._capability_to_strand: dict[str, tuple[Strand, Yarn]] = {}
        self._initialized: bool = False

    def get_settings(self, yarn_name: str) -> Any:
        """Retrieve validated settings model for any yarn by name."""
        self.initialize()
        if yarn_name in self.active_yarns:
            return self.active_yarns[yarn_name].settings
        return camshaft.get_yarn_settings(yarn_name)

    def initialize(self) -> None:
        if self._initialized:
            return
        camshaft.initialize()
        self._rebuild_active()
        self._initialized = True

    def _register_yarn_strands(
        self,
        yarn: Yarn,
        new_strands: dict[str, Strand],
        new_strand_map: dict[str, Yarn],
        new_cap_map: dict[str, tuple[Strand, Yarn]],
    ) -> None:
        """Register a single yarn's strands into Loom lookup maps."""
        for strand in reflect_strands(yarn):
            if strand.name in new_strands and not strand.capability:
                existing_yarn = new_strand_map[strand.name]
                if existing_yarn.name != yarn.name:
                    camshaft.stitch_notice(
                        level="WARNING",
                        source="loom",
                        message=(
                            f"Strand collision on '{strand.name}' between yarns "
                            f"'{existing_yarn.name}' and '{yarn.name}'"
                        ),
                        data={
                            "strand": strand.name,
                            "existing_yarn": existing_yarn.name,
                            "new_yarn": yarn.name,
                        },
                    )
                    raise StrandCollisionError(strand.name, existing_yarn.name, yarn.name)
            new_strands[strand.name] = strand
            new_strand_map[strand.name] = yarn
            if strand.capability:
                new_cap_map[strand.capability] = (strand, yarn)

    def _notify_yarn_lifecycle_events(
        self,
        old_yarns: set[str],
        new_yarns: set[str],
        new_active: dict[str, Yarn],
    ) -> None:
        """Trigger on_unload and on_load hooks for deactivated and activated yarns."""
        all_yarns = camshaft.get_all_yarns()
        for name in old_yarns - new_yarns:
            if name in all_yarns:
                with contextlib.suppress(*SAFE_EXCEPTIONS):
                    all_yarns[name].on_unload()
        for name in new_yarns - old_yarns:
            with contextlib.suppress(*SAFE_EXCEPTIONS):
                new_active[name].on_load()

    def _rebuild_active(self) -> None:
        new_active = camshaft.get_active_yarns()
        new_strands: dict[str, Strand] = {}
        new_strand_map: dict[str, Yarn] = {}
        new_cap_map: dict[str, tuple[Strand, Yarn]] = {}

        # Higher layer yarns override lower layers
        sorted_yarns = sorted(new_active.values(), key=lambda p: getattr(p, "layer", DEFAULT_LAYER))
        for yarn in sorted_yarns:
            try:
                self._register_yarn_strands(yarn, new_strands, new_strand_map, new_cap_map)
            except SAFE_EXCEPTIONS as e:
                camshaft.stitch_notice(
                    level="ERROR",
                    source="loom",
                    message=f"Failed to load yarn '{yarn.name}': {e}",
                    data={"yarn": yarn.name, "error": str(e)},
                )

        self._notify_yarn_lifecycle_events(set(self.active_yarns.keys()), set(new_active.keys()), new_active)

        self.active_yarns, self.strands = new_active, new_strands
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

    def _load_target_strand_on_demand(self, strand_name: str) -> bool:
        """Hydrate only the target yarn providing strand_name from the compiled index."""
        if strand_name in {"textile_get_state", "textile_get_engine_state", "cancel_live_task"}:
            core_yarn = camshaft.get_yarn("core")
            if core_yarn:
                self.active_yarns[core_yarn.name] = core_yarn
                self._register_yarn_strands(core_yarn, self.strands, self._strand_to_yarn, self._capability_to_strand)
                return True
            return False

        index = camshaft.read_strand_index()
        entry = index.get(strand_name)
        if not entry:
            return False

        source_file = Path(entry["source_file"])
        yarn = camshaft.probe_isolated_yarn(source_file)
        if not yarn:
            return False

        camshaft.register_yarn(yarn)
        self.active_yarns[yarn.name] = yarn
        if hasattr(yarn, "get_strands") and callable(yarn.get_strands):
            raw_strands = yarn.get_strands()
            if isinstance(raw_strands, (list, tuple)):
                target_raw = next((s for s in raw_strands if getattr(s, "name", None) == strand_name), None)
                if target_raw:
                    strand = bind_strand_to_core(yarn, target_raw)
                    self.strands[strand.name] = strand
                    self._strand_to_yarn[strand.name] = yarn
                    if strand.capability:
                        self._capability_to_strand[strand.capability] = (strand, yarn)
                    return True
        self._register_yarn_strands(yarn, self.strands, self._strand_to_yarn, self._capability_to_strand)
        return True

    def get_strand(self, strand_name: str) -> Strand | None:
        if strand_name in self.strands:
            return self.strands[strand_name]
        if self._load_target_strand_on_demand(strand_name):
            return self.strands.get(strand_name)
        self.initialize()
        return self.strands.get(strand_name)

    def get_yarn_for_strand(self, strand_name: str) -> Yarn | None:
        """Resolve active providing Yarn instance for a given strand name."""
        if strand_name in self.strands:
            resolved = self._resolve_target_strand(strand_name)
            if resolved:
                return resolved[1]
            return self._strand_to_yarn.get(strand_name)
        if self._load_target_strand_on_demand(strand_name):
            resolved = self._resolve_target_strand(strand_name)
            if resolved:
                return resolved[1]
            return self._strand_to_yarn.get(strand_name)
        self.initialize()
        resolved = self._resolve_target_strand(strand_name)
        if resolved:
            return resolved[1]
        return self._strand_to_yarn.get(strand_name)

    def _resolve_target_strand(self, strand_name: str) -> tuple[Strand, Yarn, Any] | None:
        """Resolve active strand object, providing yarn, and handler function."""
        strand = self.strands.get(strand_name)
        yarn = self._strand_to_yarn.get(strand_name)
        if not yarn or not strand:
            return None

        handler = strand.handler
        if strand.capability and strand.capability in self._capability_to_strand:
            active_s, active_y = self._capability_to_strand[strand.capability]
            if active_y.name != yarn.name:
                strand, yarn = active_s, active_y
                handler = strand.handler or handler

        return strand, yarn, handler

    def _gate_strand_execution(
        self,
        strand: Strand,
        raw_args: dict[str, Any],
        otp: str | None,
    ) -> tuple[dict[str, Any] | None, str | None]:
        """Validate arguments against schema and verify 2FA TOTP policy."""
        clean_args = raw_args.copy()
        effective_otp = otp or clean_args.pop("otp", None)
        if isinstance(effective_otp, str):
            effective_otp = effective_otp.strip()

        val_err, coerced = validate_strand_arguments(
            strand_name=strand.name,
            args=clean_args,
            schema_model=strand.args_schema,
            parameters=strand.parameters,
            required=strand.required,
        )
        if val_err:
            return None, f"Error: {val_err}"

        sec_ok, sec_err_msg = check_security_policy(strand.tier, strand.name, otp=effective_otp, reason=strand.reason)
        if not sec_ok:
            return None, f"Error: {sec_err_msg}"

        return coerced, None

    async def execute(
        self,
        strand_name: str,
        args: dict[str, Any],
        *,
        caller: str | None = None,
        otp: str | None = None,
    ) -> str:
        """Native asynchronous strand execution with zero exception throwing."""
        if strand_name not in self.strands and not self._load_target_strand_on_demand(strand_name):
            self.initialize()
        resolved = self._resolve_target_strand(strand_name)
        if not resolved:
            return f"Error: Strand '{strand_name}' not found or no provider yarn is enabled."

        strand, yarn, _handler = resolved
        clean_args, gate_error = self._gate_strand_execution(strand, args, otp)
        if gate_error is not None or clean_args is None:
            return gate_error or "Error: Invalid arguments"

        effective_caller = caller or os.getenv("TEXTILE_CALLER", "")
        task_id = str(uuid.uuid4())[:8]
        tier_val = strand.tier.value if hasattr(strand.tier, "value") else str(strand.tier)

        camshaft.emit_execution_started(
            task_id=task_id,
            strand_name=strand_name,
            args=clean_args,
            tier_val=tier_val,
            caller=effective_caller,
        )

        t0 = time.perf_counter()
        success = True
        err = None
        try:
            if (
                getattr(yarn, "name", "") == "core"
                or getattr(yarn.__class__, "__module__", "") == "unittest.mock"
                or (strand.raw_handler is None and callable(strand.handler))
            ):
                res = await execute_in_process(strand, clean_args)
            else:
                res = await execute_strand_async(
                    yarn,
                    strand.name,
                    clean_args,
                    timeout=strand.timeout,
                    tier=strand.tier,
                )
            res_str = str(res)
            if res_str.startswith("Error: "):
                success = False
                err = res_str[7:]
            return res_str
        except (OSError, RuntimeError, ValueError, TypeError, KeyError, TimeoutError) as e:
            success = False
            err = str(e)
            return f"Error executing strand '{strand_name}': {e}"
        finally:
            dur = (time.perf_counter() - t0) * 1000.0
            camshaft.emit_execution_completed(
                task_id=task_id,
                strand_name=strand_name,
                args=clean_args,
                tier_val=tier_val,
                caller=effective_caller,
                duration_ms=dur,
                success=success,
                error=err,
            )

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
                return pool.submit(asyncio.run, self.execute(strand_name, args, caller=caller, otp=otp)).result()
        return asyncio.run(self.execute(strand_name, args, caller=caller, otp=otp))


loom = Loom()
loom_mesh = loom
LoomMesh = Loom


@camshaft.on("strand_execute_input")
async def _on_strand_execute_input(
    _sender: Any = None,
    *,
    name: str,
    args: dict[str, Any],
    caller: str | None = None,
    otp: str | None = None,
    **_kw: Any,
) -> str:
    return await loom.execute(name, args, caller=caller, otp=otp)


@camshaft.on("yarn_status_changed")
def _on_yarn_changed(_sender: Any = None, **_kw: Any) -> None:
    loom._rebuild_active()
