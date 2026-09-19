"""
Textile Loom - High-Performance Strand Execution, Capability Resolution, and Dispatch Engine.
"""

import asyncio
import inspect
import logging
from typing import Any, Dict, List, Optional, Tuple

from textile.core.base import BaseYarn, Strand, Weft, LAYER_BASE
from textile.core.skein import skein, Skein

logger = logging.getLogger(__name__)


class Loom:
    """Central runtime dispatch engine managing layer-tier capability overriding and execution."""

    def __init__(self, registry: Optional[Skein] = None):
        self._skein = registry or skein
        self.active_yarns: Dict[str, BaseYarn] = {}
        self.strands: Dict[str, Strand] = {}
        self.wefts: List[Weft] = []
        self._strand_to_yarn: Dict[str, BaseYarn] = {}
        self._capability_to_strand: Dict[str, Tuple[Strand, BaseYarn]] = {}
        self._initialized: bool = False

    def initialize(self) -> None:
        if self._initialized:
            return
        self._skein.initialize()
        self._rebuild_active()
        self._initialized = True

    def _rebuild_active(self) -> None:
        new_active = self._skein.get_active_yarns()
        new_strands: Dict[str, Strand] = {}
        new_wefts: List[Weft] = []
        new_strand_map: Dict[str, BaseYarn] = {}
        new_cap_map: Dict[str, Tuple[Strand, BaseYarn]] = {}

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

    def get_strand_override_status(self, strand: Strand, yarn: BaseYarn) -> Tuple[bool, Optional[str], Optional[str]]:
        if strand.capability and strand.capability in self._capability_to_strand:
            active_s, active_y = self._capability_to_strand[strand.capability]
            if active_y.name != yarn.name:
                return True, active_y.name, strand.capability
        return False, None, None

    def get_all_strands(self) -> List[Strand]:
        self.initialize()
        return [
            s for name, s in self.strands.items()
            if not (self._strand_to_yarn.get(name) and self.get_strand_override_status(s, self._strand_to_yarn[name])[0])
        ]

    def get_strand(self, strand_name: str) -> Optional[Strand]:
        self.initialize()
        return self.strands.get(strand_name)

    def get_mcp_definitions(self) -> List[Dict[str, Any]]:
        self.initialize()
        return [strand.to_mcp_definition() for strand in self.get_all_strands()]

    async def execute(self, strand_name: str, args: Dict[str, Any], caller: Optional[str] = None) -> str:
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
        from textile.core.warp import warp, WarpEvent

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

    def execute_sync(self, strand_name: str, args: Dict[str, Any], caller: Optional[str] = None) -> str:
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

    def execute_strand(self, strand_name: str, args: Dict[str, Any], caller: Optional[str] = None) -> str:
        """Backward-compatible synchronous execution alias."""
        return self.execute_sync(strand_name, args, caller=caller)

    async def execute_strand_async(self, strand_name: str, args: Dict[str, Any], caller: Optional[str] = None) -> str:
        """Backward-compatible asynchronous execution alias."""
        return await self.execute(strand_name, args, caller=caller)

    def get_all_wefts(self) -> List[Weft]:
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
        """Dynamically generate fabric-level instructions and weft contract guidance for MCP clients."""
        self.initialize()
        active_yarn_names = list(self.active_yarns.keys())
        lines = [
            "Textile Linux Desktop Automation & Intelligence Fabric Active.",
            f"Active Capability Yarns: {', '.join(active_yarn_names)}.",
            "",
            "## Yarn Contracts & Real-Time Stream Attunements",
            "The following active yarns listen for inline semantic tokens in your natural language stream.",
            "Fulfilling these contracts is advisory and strongly recommended to deliver a seamless, delightful user experience:",
        ]

        if "canvas" in self.active_yarns:
            lines.extend([
                "",
                "### Canvas Emotive Desktop Avatar Contract",
                "- You possess an animated 60 FPS emotive desktop avatar present on the user's screen.",
                "- You are strongly encouraged to interleave 2-4 semantic mood and gaze tags across your spoken/written sentences:",
                "  * Mood tags: <mood:neutral>, <mood:happy>, <mood:excited>, <mood:celebrating>, <mood:thinking>, <mood:focused>, <mood:listening>, <mood:curious>, <mood:calm>, <mood:shy>, <mood:mischievous>, <mood:confused>, <mood:surprised>, <mood:alert>, <mood:sleepy>, <mood:error>, <mood:glitch>",
                "  * Gaze tags: <gaze:X,Y> (where X: -16.0 to 16.0, Y: -12.0 to 12.0, e.g. <gaze:8.0,-5.0> to look up-right)",
                "- Example: \"<mood:curious> Let's look into that for you... <mood:thinking> inspecting files now... <mood:happy> Found it!\"",
                "- The avatar automatically pulses harmonic forehead gemstone ripples when system tools are channeled.",
            ])

        for weft in self.wefts:
            if weft.name not in ("on_stream_mood", "on_stream_gaze") and weft.description:
                lines.append(f"- Weft `{weft.name}`: {weft.description}")

        lines.extend([
            "",
            "## General Desktop Safety Guidelines",
            "- Pre-authorized desktop and POSIX operations run smoothly across D-Bus, AT-SPI, and PolicyKit.",
            "- Always verify context when performing disruptive actions.",
        ])

        return "\n".join(lines)


loom = Loom()

