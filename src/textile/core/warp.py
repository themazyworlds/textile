"""
Textile Warp - Universal Real-Time Pub/Sub Sensory & Event Bus.
"""

import logging
from enum import Enum
from typing import Any, Callable, Dict, List, Union

logger = logging.getLogger(__name__)


class WarpEvent(str, Enum):
    """Standard Core Event Topics."""
    USER_INPUT_PROMPT = "user.input.prompt"
    TOOL_EXECUTION_START = "tool.execution.start"
    TOOL_EXECUTION_DONE = "tool.execution.done"
    STATE_CHANGE = "state.change"
    MOOD_CHANGE = "mood.change"
    VOICE_STATE = "voice.state"
    DESKTOP_EVENT = "desktop.event"


Topic = Union[WarpEvent, str]


class Warp:
    """Universal string-and-enum Pub/Sub Event Bus for desktop sensory streaming."""

    def __init__(self):
        self._subscribers: Dict[str, List[Callable[[Any], None]]] = {}

    def _normalize_topic(self, topic: Topic) -> str:
        return topic.value if isinstance(topic, WarpEvent) else str(topic).strip()

    def subscribe(self, topic: Topic, callback: Callable[[Any], None]):
        key = self._normalize_topic(topic)
        if key not in self._subscribers:
            self._subscribers[key] = []
        if callback not in self._subscribers[key]:
            self._subscribers[key].append(callback)

    def unsubscribe(self, topic: Topic, callback: Callable[[Any], None]):
        key = self._normalize_topic(topic)
        if key in self._subscribers and callback in self._subscribers[key]:
            self._subscribers[key].remove(callback)

    def publish(self, topic: Topic, data: Any = None):
        key = self._normalize_topic(topic)
        for cb in list(self._subscribers.get(key, [])):
            try:
                cb(data)
            except Exception as e:
                logger.debug(f"Warp subscriber error on '{key}': {e}")


warp = Warp()
