"""
Textile Stream Processing Engine.
Provides real-time regex attunement matching, argument coercion, and token stripping for text streams.
"""

import asyncio
import contextlib
import inspect
from typing import Any

from textile.core.definitions.errors import SAFE_EXCEPTIONS
from textile.core.execution.strands import Weft
from textile.core.telemetry.log import get_logger

logger = get_logger(__name__)

__all__ = ["StreamEngine", "stream_engine"]


class StreamEngine:
    """Real-time Weft text stream attunement processor with chunk boundary buffering."""

    def __init__(self) -> None:
        self._buffer: str = ""

    def _collect_weft_matches(self, text: str, wefts: list[Weft]) -> list[tuple[int, int, Weft, Any]]:
        """Collect and chronologically sort all regex matches across active Wefts."""
        all_matches = []
        for weft in wefts:
            all_matches.extend(
                (m.start(), -weft.priority, weft, m) for m in weft.pattern.finditer(text)
            )
        all_matches.sort(key=lambda x: (x[0], x[1]))
        return all_matches

    def _strip_weft_tokens(self, text: str, wefts: list[Weft]) -> str:
        """Strip matched attunement tokens from text stream."""
        result = text
        for weft in wefts:
            if weft.strip:
                result = weft.pattern.sub("", result)
        return result

    def process_stream(self, chunk: str, wefts: list[Weft]) -> str:
        """Synchronously process streaming text chunk through active Wefts with chunk buffering."""
        if not chunk and not self._buffer:
            return ""
        if not wefts:
            res = self._buffer + (chunk or "")
            self._buffer = ""
            return res

        self._buffer += chunk or ""
        text_to_process = self._buffer

        for _, _, weft, match in self._collect_weft_matches(text_to_process, wefts):
            try:
                res = weft.execute_match(match)
                if inspect.iscoroutine(res):
                    with contextlib.suppress(RuntimeError):
                        loop = asyncio.get_running_loop()
                        loop.create_task(res)
                    if not inspect.iscoroutinefunction(res):
                        asyncio.run(res)
            except SAFE_EXCEPTIONS as e:
                logger.error("stream.weft_execution_failed", weft=weft.name, error=str(e))

        cleaned = self._strip_weft_tokens(text_to_process, wefts)
        # If text ends with an unclosed bracket '<', buffer it for the next chunk
        if "<" in cleaned and ">" not in cleaned[cleaned.rfind("<") :]:
            split_pos = cleaned.rfind("<")
            emitted, self._buffer = cleaned[:split_pos], cleaned[split_pos:]
            return emitted
        self._buffer = ""
        return cleaned

    async def process_stream_async(self, chunk: str, wefts: list[Weft]) -> str:
        """Asynchronously process streaming text chunk through active Wefts with chunk buffering."""
        if not chunk and not self._buffer:
            return ""
        if not wefts:
            res = self._buffer + (chunk or "")
            self._buffer = ""
            return res

        self._buffer += chunk or ""
        text_to_process = self._buffer

        for _, _, weft, match in self._collect_weft_matches(text_to_process, wefts):
            try:
                res = weft.execute_match(match)
                if inspect.iscoroutine(res):
                    await res
            except SAFE_EXCEPTIONS as e:
                logger.error("stream.weft_execution_failed", weft=weft.name, error=str(e))

        cleaned = self._strip_weft_tokens(text_to_process, wefts)
        if "<" in cleaned and ">" not in cleaned[cleaned.rfind("<") :]:
            split_pos = cleaned.rfind("<")
            emitted, self._buffer = cleaned[:split_pos], cleaned[split_pos:]
            return emitted
        self._buffer = ""
        return cleaned

    def reset(self) -> None:
        """Reset internal stream chunk buffer."""
        self._buffer = ""


stream_engine = StreamEngine()
