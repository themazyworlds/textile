"""
Textile Quill - Command-Line Interface (CLI) Dispatcher & Interactive Command Driver.
"""

import asyncio
import functools
import inspect
from collections.abc import Callable
from typing import Any
lazy import concurrent.futures

import typer


class AsyncTyper(typer.Typer):
    """Typer subclass that provides seamless support for `async def` commands and callbacks."""

    def command(self, *args: Any, **kwargs: Any) -> Callable[..., Any]:
        decorator = super().command(*args, **kwargs)

        def wrapper(f: Callable[..., Any]) -> Callable[..., Any]:
            if inspect.iscoroutinefunction(f):

                @functools.wraps(f)
                def runner(*f_args: Any, **f_kwargs: Any) -> Any:
                    try:
                        loop = asyncio.get_running_loop()
                    except RuntimeError:
                        loop = None

                    if loop and loop.is_running():
                        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                            return pool.submit(asyncio.run, f(*f_args, **f_kwargs)).result()

                    return asyncio.run(f(*f_args, **f_kwargs))

                return decorator(runner)
            return decorator(f)

        return wrapper

    def callback(self, *args: Any, **kwargs: Any) -> Callable[..., Any]:
        decorator = super().callback(*args, **kwargs)

        def wrapper(f: Callable[..., Any]) -> Callable[..., Any]:
            if inspect.iscoroutinefunction(f):

                @functools.wraps(f)
                def runner(*f_args: Any, **f_kwargs: Any) -> Any:
                    try:
                        loop = asyncio.get_running_loop()
                    except RuntimeError:
                        loop = None

                    if loop and loop.is_running():
                        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                            return pool.submit(asyncio.run, f(*f_args, **f_kwargs)).result()

                    return asyncio.run(f(*f_args, **f_kwargs))

                return decorator(runner)
            return decorator(f)

        return wrapper


quill = AsyncTyper(
    name="quill",
    help="Quill - Interactive Command Driver for the Textile Linux Desktop AI Subsystem.",
    add_completion=True,
    no_args_is_help=True,
)

__all__ = ["AsyncTyper", "quill"]
