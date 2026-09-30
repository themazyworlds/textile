"""
Textile Engine Command-Line Interface (CLI) Package.
Provides discovery, layer hierarchy, strand inspection, execution, IPC, and health diagnostics.
"""

from textile.core.cli.app import (
    SeamsAuditReportModel,
    SeamsSummaryModel,
    TapestryStateModel,
    app,
    console,
    ensure_initialized,
)
from textile.core.cli.commands import daemons, execution, registry

__all__ = [
    "SeamsAuditReportModel",
    "SeamsSummaryModel",
    "TapestryStateModel",
    "app",
    "console",
    "daemons",
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
