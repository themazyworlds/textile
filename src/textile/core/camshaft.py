"""
Textile Camshaft - Engine Signal Coordinator.
Assembles domain event mixins, signal registries, and subscription facades into the unified camshaft singleton.
"""

from collections.abc import Callable
from typing import Any

lazy import blinker

from textile.core.loom._mixin import LoomMixin
from textile.core.skein._mixin import SkeinMixin
from textile.core.tapestry._mixin import TapestryMixin
from textile.core.twill._mixin import TwillMixin
lazy from textile.core.bootstrap import bootstrap
lazy from textile.core.bus import bus, emit, emit_async, request, request_async


def ensure_bootstrapped() -> None:
    """Ensure engine subsystems have booted into memory via the bootstrapper."""
    bootstrap()


class CamshaftSignals:
    """Unified signal registry aggregating all domain signals across Camshaft mixins."""

    def __init__(self, *mixin_classes: type) -> None:
        self._name_map: dict[str, Any] = {}
        for cls in mixin_classes:
            self.register_mixin(cls)

    def register_mixin(self, cls: type) -> None:
        """Register all signals defined in an inner *Signals class of a mixin."""
        for attr in dir(cls):
            if attr.endswith("Signals"):
                signals_cls = getattr(cls, attr, None)
                if isinstance(signals_cls, type):
                    for key, val in vars(signals_cls).items():
                        if not key.startswith("_") and isinstance(val, blinker.Signal):
                            setattr(self, key, val)
                            self._name_map[key] = val
                            sig_name = getattr(val, "name", None)
                            if sig_name:
                                self._name_map[sig_name] = val

    def __getattr__(self, name: str) -> blinker.Signal:
        if name in self._name_map:
            return self._name_map[name]
        sig = bus.signal(name)
        self._name_map[name] = sig
        setattr(self, name, sig)
        return sig

    def resolve(self, signal: Any) -> Any:
        """Resolve a signal instance from a name string or Signal object."""
        if hasattr(signal, "connect") and hasattr(signal, "send"):
            return signal
        if isinstance(signal, str):
            if signal in self._name_map:
                return self._name_map[signal]
            return bus.signal(signal)
        raise ValueError(f"Cannot resolve signal: {signal!r}")

    def __getitem__(self, key: str) -> Any:
        return self.resolve(key)

    def __contains__(self, key: str) -> bool:
        return key in self._name_map


class Camshaft(
    LoomMixin,
    SkeinMixin,
    TapestryMixin,
    TwillMixin,
):
    """Game-engine signal coordinator, error dispatcher, and reactive subscription facade."""

    signals: CamshaftSignals = CamshaftSignals()

    @staticmethod
    def initialize() -> None:
        """Explicitly boot engine subsystems into memory."""
        ensure_bootstrapped()

    @classmethod
    def resolve_signal(cls, signal: Any) -> Any:
        """Resolve a signal object from an attribute, short name, or full bus name."""
        return cls.signals.resolve(signal)

    @classmethod
    def on(
        cls,
        signal: Any,
        *,
        sender: Any = None,
        **connect_kwargs: Any,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Decorator to connect a subscriber callback to a signal channel.

        Usage:
            @camshaft.on("strand_execution_completed")
            def handler(sender, **kwargs): ...

            @camshaft.on(camshaft.signals.broadcast_event)
            def on_telemetry(sender, **kwargs): ...
        """
        sig = cls.resolve_signal(signal)
        sender_target = blinker.ANY if sender is None else sender

        def decorator(receiver: Callable[..., Any]) -> Callable[..., Any]:
            sig.connect(receiver, sender=sender_target, **connect_kwargs)
            return receiver

        return decorator

    @classmethod
    def connect(
        cls,
        signal: Any,
        receiver: Callable[..., Any] | None = None,
        *,
        sender: Any = None,
        **connect_kwargs: Any,
    ) -> Any:
        """Connect a subscriber callback to a signal channel, or return a decorator if receiver is None."""
        sig = cls.resolve_signal(signal)
        sender_target = blinker.ANY if sender is None else sender
        if receiver is None:

            def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
                sig.connect(fn, sender=sender_target, **connect_kwargs)
                return fn

            return decorator
        return sig.connect(receiver, sender=sender_target, **connect_kwargs)

    @classmethod
    def disconnect(
        cls,
        signal: Any,
        receiver: Callable[..., Any],
        *,
        sender: Any = None,
    ) -> None:
        """Disconnect a subscriber callback from a signal channel."""
        sig = cls.resolve_signal(signal)
        sender_target = blinker.ANY if sender is None else sender
        sig.disconnect(receiver, sender=sender_target)

    @classmethod
    def emit(cls, signal: Any, sender: Any = "camshaft", **kwargs: Any) -> list[Any]:
        """Emit a signal synchronously through the engine bus."""
        sig = cls.resolve_signal(signal)
        return emit(sig, sender=sender, **kwargs)

    @classmethod
    async def emit_async(cls, signal: Any, sender: Any = "camshaft", **kwargs: Any) -> list[Any]:
        """Emit a signal asynchronously through the engine bus."""
        sig = cls.resolve_signal(signal)
        return await emit_async(sig, sender=sender, **kwargs)

    @classmethod
    def request(cls, signal: Any, sender: Any = "camshaft", **kwargs: Any) -> Any:
        """Send a synchronous request across a signal channel."""
        sig = cls.resolve_signal(signal)
        return request(sig, sender=sender, **kwargs)

    @classmethod
    async def request_async(cls, signal: Any, sender: Any = "camshaft", **kwargs: Any) -> Any:
        """Send an asynchronous request across a signal channel."""
        sig = cls.resolve_signal(signal)
        return await request_async(sig, sender=sender, **kwargs)


camshaft = Camshaft()

# Auto-register all signals defined across all mixin base classes
for _base in Camshaft.__bases__:
    Camshaft.signals.register_mixin(_base)

__all__ = ["Camshaft", "CamshaftSignals", "camshaft", "ensure_bootstrapped"]
