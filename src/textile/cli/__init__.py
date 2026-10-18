"""
Textile Engine Command-Line Interface (CLI) Package.
Provides discovery, layer hierarchy, strand inspection, execution, IPC, and health diagnostics.
"""

from textile.cli import commands
from textile.cli.quill import quill
lazy from textile.cli.ui import console

__all__ = [
    "commands",
    "console",
    "main",
    "quill",
]


def main():
    """CLI entrypoint function invoked by textile script."""
    quill()


if __name__ == "__main__":
    main()
