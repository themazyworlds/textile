"""
Textile Loom - High-Performance Strand Execution, Capability Resolution, and Dispatch Engine.
"""

import asyncio
import inspect
import logging
from typing import Any

from textile.core.base import LAYER_BASE, Yarn, Strand, Weft
from textile.core.skein import Skein, skein

logger = logging.getLogger(__name__)


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

    def _rebuild_active(self) -> None:
        new_active = self._skein.get_active_yarns()
        new_strands: dict[str, Strand] = {}
        new_wefts: list[Weft] = []
        new_strand_map: dict[str, Yarn] = {}
        new_cap_map: dict[str, tuple[Strand, Yarn]] = {}

        # Higher layer yarns override lower layers
        for yarn in sorted(new_active.values(), key=lambda p: getattr(p, "layer", LAYER_BASE)):
            try:
                for strand in yarn.get_strands():
                    new_strands[strand.name] = strand
                    new_strand_map[strand.name] = yarn
                    if strand.capability:
                        new_cap_map[strand.capability] = (strand, yarn)
                for weft in yarn.get_wefts():
                    new_wefts.append(weft)
            except Exception as e:
                logger.error(f"Error loading strands/wefts from yarn {yarn.name}: {e}")

        # Sort wefts by priority (higher priority first)
        new_wefts.sort(key=lambda w: w.priority, reverse=True)

        # Lifecycle notifications
        old_keys, new_keys = set(self.active_yarns.keys()), set(new_active.keys())
        for name in old_keys - new_keys:
            if name in self._skein.all_yarns:
                try: self._skein.all_yarns[name].on_unload()
                except Exception: pass
        for name in new_keys - old_keys:
            try: new_active[name].on_load()
            except Exception: pass

        self.active_yarns, self.strands, self.wefts = new_active, new_strands, new_wefts
        self._strand_to_yarn, self._capability_to_strand = new_strand_map, new_cap_map

    def get_strand_override_status(self, strand: Strand, yarn: Yarn) -> tuple[bool, str | None, str | None]:
        if strand.capability and strand.capability in self._capability_to_strand:
            active_s, active_y = self._capability_to_strand[strand.capability]
            if active_y.name != yarn.name:
                return True, active_y.name, strand.capability
        return False, None, None

    def get_all_strands(self) -> list[Strand]:
        self.initialize()
        return [
            s for name, s in self.strands.items()
            if not (self._strand_to_yarn.get(name) and self.get_strand_override_status(s, self._strand_to_yarn[name])[0])
        ]

    def get_strand(self, strand_name: str) -> Strand | None:
        self.initialize()
        return self.strands.get(strand_name)

    def get_mcp_definitions(self) -> list[dict[str, Any]]:
        self.initialize()
        return [strand.to_mcp_definition() for strand in self.get_all_strands()]

    async def execute(self, strand_name: str, args: dict[str, Any], caller: str | None = None) -> str:
        """Native asynchronous strand execution."""
        self.initialize()
        strand = self.strands.get(strand_name)
        yarn = self._strand_to_yarn.get(strand_name)
        if not yarn or not strand or not strand.handler:
            return f"Error: Strand '{strand_name}' not found or no provider yarn is enabled."

        if strand.capability and strand.capability in self._capability_to_strand:
            active_s, active_y = self._capability_to_strand[strand.capability]
            if active_y.name != yarn.name:
                strand, yarn = active_s, active_y

        import os
        import time
        import uuid

        from textile.core.tapestry import core_tapestry
        from textile.core.warp import WarpEvent, warp

        effective_caller = caller or os.getenv("TEXTILE_CALLER", "")
        task_id = str(uuid.uuid4())[:8]
        core_tapestry.record_task_start(task_id, strand_name, args)
        warp.publish(WarpEvent.TOOL_EXECUTION_START, {"task_id": task_id, "strand": strand_name, "caller": effective_caller})
        t0 = time.perf_counter()
        success = True
        err = None
        try:
            if inspect.iscoroutinefunction(strand.handler):
                return await strand.handler(args)
            return await asyncio.to_thread(strand.handler, args)
        except Exception as e:
            success = False
            err = str(e)
            raise
        finally:
            dur = (time.perf_counter() - t0) * 1000.0
            core_tapestry.record_task_end(task_id, success=success, duration_ms=dur, error=err)
            warp.publish(WarpEvent.TOOL_EXECUTION_DONE, {"task_id": task_id, "strand": strand_name, "success": success, "duration_ms": dur, "caller": effective_caller})

    def execute_sync(self, strand_name: str, args: dict[str, Any], caller: str | None = None) -> str:
        """Synchronous bridge for CLI and non-async environments."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(asyncio.run, self.execute(strand_name, args, caller=caller)).result()
        return asyncio.run(self.execute(strand_name, args, caller=caller))

    def execute_strand(self, strand_name: str, args: dict[str, Any], caller: str | None = None) -> str:
        """Backward-compatible synchronous execution alias."""
        return self.execute_sync(strand_name, args, caller=caller)

    async def execute_strand_async(self, strand_name: str, args: dict[str, Any], caller: str | None = None) -> str:
        """Backward-compatible asynchronous execution alias."""
        return await self.execute(strand_name, args, caller=caller)

    def get_all_wefts(self) -> list[Weft]:
        """Return all active Weft attunements sorted by priority."""
        self.initialize()
        return list(self.wefts)

    def process_stream(self, chunk: str) -> str:
        """Process real-time streaming text chunk through active Weft attunements.

        Matches regex patterns, dispatches type-coerced arguments to attunement handlers,
        and strips matched attunement tokens from the returned text.
        """
        self.initialize()
        if not chunk or not self.wefts:
            return chunk

        # Collect all matches across active wefts
        all_matches = []
        for weft in self.wefts:
            for m in weft.pattern.finditer(chunk):
                all_matches.append((m.start(), -weft.priority, weft, m))

        # Sort chronologically by position in the text stream
        all_matches.sort(key=lambda x: (x[0], x[1]))

        for _, _, weft, match in all_matches:
            try:
                res = weft.execute_match(match)
                if inspect.iscoroutine(res):
                    try:
                        loop = asyncio.get_running_loop()
                        loop.create_task(res)
                    except RuntimeError:
                        asyncio.run(res)
            except Exception as e:
                logger.error(f"Error executing weft '{weft.name}': {e}")

        result = chunk
        for weft in self.wefts:
            if weft.strip:
                result = weft.pattern.sub("", result)

        return result

    async def process_stream_async(self, chunk: str) -> str:
        """Asynchronous streaming text processor for active Wefts."""
        self.initialize()
        if not chunk or not self.wefts:
            return chunk

        all_matches = []
        for weft in self.wefts:
            for m in weft.pattern.finditer(chunk):
                all_matches.append((m.start(), -weft.priority, weft, m))

        all_matches.sort(key=lambda x: (x[0], x[1]))

        for _, _, weft, match in all_matches:
            try:
                res = weft.execute_match(match)
                if inspect.iscoroutine(res):
                    await res
            except Exception as e:
                logger.error(f"Error executing weft '{weft.name}': {e}")

        result = chunk
        for weft in self.wefts:
            if weft.strip:
                result = weft.pattern.sub("", result)

    def get_fabric_instructions(self) -> str:
        """Deliver all active yarn contracts and weft attunements to the MCP client (postman pattern)."""
        self.initialize()
        letters = []
        for name, yarn in self.active_yarns.items():
            letter = yarn.get_contract()
            if letter:
                pub_tag = f"[{yarn.publisher}/{name}]" if yarn.publisher else f"[{name}]"
                letters.append(f"### Yarn Contract {pub_tag}\n{letter.strip()}")

            for weft in yarn.get_wefts():
                if weft.description and (not letter or weft.description not in letter):
                    letters.append(f"- Weft Stream Attunement `{weft.name}`: {weft.description}")

        if not letters:
            return ""

        active_yarn_names = list(self.active_yarns.keys())
        header = (
            "Textile Linux Desktop Automation & Intelligence Fabric Active.\n"
            f"Active Capability Yarns: {', '.join(active_yarn_names)}.\n\n"
            "## Active Yarn Contracts & Real-Time Stream Attunements\n"
            "The following active yarns have delivered their behavioral contracts and stream attunements for this session.\n"
            "Fulfilling these contracts is advisory and strongly recommended to deliver a seamless, delightful user experience:\n"
        )
        return header + "\n" + "\n\n".join(letters)


loom = Loom()

