"""
Textile Engine Command-Line Interface (CLI) Package.
Provides discovery, layer hierarchy, strand inspection, execution, IPC, and health diagnostics.
"""

from textile.core.cli.app import (
    TapestryStateModel,
    app,
    console,
    ensure_initialized,
)
from textile.core.cli.commands import execution, registry

__all__ = [
    "TapestryStateModel",
    "app",
    "console",
    "ensure_initialized",
    "execution",
    "main",
    "registry",
]


def main():
    """CLI entrypoint function invoked by textile script."""
    app()


if __name__ == "__main__":
    main()
