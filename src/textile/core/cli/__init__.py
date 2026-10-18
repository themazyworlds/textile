"""
Textile Engine Command-Line Interface (CLI) Package.
Provides discovery, layer hierarchy, strand inspection, execution, IPC, and health diagnostics.
"""

from textile.core.cli.app import app
from textile.core.cli.commands import execution, registry
lazy from textile.core.cli.ui import console

__all__ = [
    "app",
    "console",
    "execution",
    "main",
    "registry",
]


def main():
    """CLI entrypoint function invoked by textile script."""
    app()


if __name__ == "__main__":
    main()
