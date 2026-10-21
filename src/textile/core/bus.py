"""
Textile Event Bus Anchor & Core Dispatchers.
Lightweight anchor providing central signal namespace and request/emit primitives.
"""

from typing import Any

lazy import blinker

lazy from textile.core.camshaft import ensure_bootstrapped

# The single, unified signal bus for the entire engine
bus = blinker.Namespace()


async def request_async(signal: blinker.Signal | str, sender: Any = "textile", **kwargs: Any) -> Any:
    """Send an async request across a signal channel and return the first non-None handler result."""
    ensure_bootstrapped()
    sig = bus.signal(signal) if isinstance(signal, str) else signal
    results = await sig.send_async(sender, **kwargs)
    for _receiver, value in results:
        if value is not None:
            return value
    return None


def request(signal: blinker.Signal | str, sender: Any = "textile", **kwargs: Any) -> Any:
    """Send a synchronous request across a signal channel and return the first non-None handler result."""
    ensure_bootstrapped()
    sig = bus.signal(signal) if isinstance(signal, str) else signal
    results = sig.send(sender, **kwargs)
    for _receiver, value in results:
        if value is not None:
            return value
    return None


def emit(signal: blinker.Signal | str, sender: Any = "textile", **kwargs: Any) -> list[Any]:
    """Emit a broadcast signal to all connected subscribers and collect all returned values."""
    ensure_bootstrapped()
    sig = bus.signal(signal) if isinstance(signal, str) else signal
    results = sig.send(sender, **kwargs)
    return [r[1] for r in results]


async def emit_async(signal: blinker.Signal | str, sender: Any = "textile", **kwargs: Any) -> list[Any]:
    """Asynchronously emit a broadcast signal to all connected subscribers."""
    ensure_bootstrapped()
    sig = bus.signal(signal) if isinstance(signal, str) else signal
    results = await sig.send_async(sender, **kwargs)
    return [r[1] for r in results]


__all__ = ["bus", "emit", "emit_async", "request", "request_async"]
