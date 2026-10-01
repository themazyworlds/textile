"""
Textile Stream Processing Engine.
Provides real-time regex attunement matching, argument coercion, and token stripping for text streams.
"""

import asyncio
import contextlib
import inspect
from typing import Any

from textile.core.execution.strands import Weft
from textile.core.telemetry.log import get_logger

logger = get_logger(__name__)

__all__ = ["StreamEngine", "stream_engine"]


class StreamEngine:
    """Real-time Weft text stream attunement processor."""

    def _collect_weft_matches(self, chunk: str, wefts: list[Weft]) -> list[tuple[int, int, Weft, Any]]:
        """Collect and chronologically sort all regex matches across active Wefts."""
        all_matches = []
        for weft in wefts:
            all_matches.extend(
                (m.start(), -weft.priority, weft, m) for m in weft.pattern.finditer(chunk)
            )
        all_matches.sort(key=lambda x: (x[0], x[1]))
        return all_matches

    def _strip_weft_tokens(self, chunk: str, wefts: list[Weft]) -> str:
        """Strip matched attunement tokens from text stream."""
        result = chunk
        for weft in wefts:
            if weft.strip:
                result = weft.pattern.sub("", result)
        return result

    def process_stream(self, chunk: str, wefts: list[Weft]) -> str:
        """Synchronously process streaming text chunk through active Wefts."""
        if not chunk or not wefts:
            return chunk or ""

        for _, _, weft, match in self._collect_weft_matches(chunk, wefts):
            try:
                res = weft.execute_match(match)
                if inspect.iscoroutine(res):
                    with contextlib.suppress(RuntimeError):
                        loop = asyncio.get_running_loop()
                        loop.create_task(res)
                    if not inspect.iscoroutinefunction(res):
                        asyncio.run(res)
            except (AttributeError, TypeError, ValueError, KeyError, OSError, RuntimeError) as e:
                logger.error("stream.weft_execution_failed", weft=weft.name, error=str(e))

        return self._strip_weft_tokens(chunk, wefts)

    async def process_stream_async(self, chunk: str, wefts: list[Weft]) -> str:
        """Asynchronously process streaming text chunk through active Wefts."""
        if not chunk or not wefts:
            return chunk or ""

        for _, _, weft, match in self._collect_weft_matches(chunk, wefts):
            try:
                res = weft.execute_match(match)
                if inspect.iscoroutine(res):
                    await res
            except (AttributeError, TypeError, ValueError, KeyError, OSError, RuntimeError) as e:
                logger.error("stream.weft_execution_failed", weft=weft.name, error=str(e))

        return self._strip_weft_tokens(chunk, wefts)


stream_engine = StreamEngine()
