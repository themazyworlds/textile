"""
Textile Warp - Universal Real-Time Pub/Sub Sensory & Event Bus.
Powered by pyee EventEmitter.
"""

import logging
from collections.abc import Callable
from enum import StrEnum
from typing import Any

from pyee.base import EventEmitter

logger = logging.getLogger(__name__)


class WarpEvent(StrEnum):
    """Standard Core Event Topics."""
    USER_INPUT_PROMPT = "user.input.prompt"
    TOOL_EXECUTION_START = "tool.execution.start"
    TOOL_EXECUTION_DONE = "tool.execution.done"
    STATE_CHANGE = "state.change"
    MOOD_CHANGE = "mood.change"
    VOICE_STATE = "voice.state"
    DESKTOP_EVENT = "desktop.event"


Topic = WarpEvent | str


class Warp:
    """Universal string-and-enum Pub/Sub Event Bus powered by pyee EventEmitter."""

    def __init__(self):
        self._ee = EventEmitter()

    def _normalize_topic(self, topic: Topic) -> str:
        return topic.value if isinstance(topic, WarpEvent) else str(topic).strip()

    def subscribe(self, topic: Topic, callback: Callable[[Any], None]) -> Callable[[Any], None]:
        key = self._normalize_topic(topic)
        self._ee.on(key, callback)
        return callback

    def unsubscribe(self, topic: Topic, callback: Callable[[Any], None]) -> None:
        key = self._normalize_topic(topic)
        self._ee.remove_listener(key, callback)

    def publish(self, topic: Topic, data: Any = None) -> None:
        key = self._normalize_topic(topic)
        try:
            self._ee.emit(key, data)
        except (AttributeError, TypeError, ValueError, KeyError, OSError, RuntimeError) as e:
            logger.debug("Warp subscriber error on '%s': %s", key, e)


warp = Warp()
