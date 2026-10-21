"""
Textile Engine Command-Line Interface (CLI) Package.
Provides discovery, layer hierarchy, strand inspection, execution, IPC, and health diagnostics.
"""

from typing import Any
lazy import asyncio

from textile.cli import commands
from textile.cli.quill import quill
lazy from textile.cli.ui import console

__all__ = [
    "async_main",
    "commands",
    "console",
    "main",
    "quill",
]


def main():
    """CLI entrypoint function invoked by quill script."""
    quill()


async def async_main(args: list[str] | None = None) -> Any:
    """Asynchronous CLI entrypoint function."""
    return await asyncio.to_thread(quill, args)


if __name__ == "__main__":
    main()
