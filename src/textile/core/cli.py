"""
Textile Core CLI Entry Point.
Routes commands to textile.core.cli_typer.app.
"""

from textile.core.cli_typer import _layer_info, app, main

__all__ = ["app", "main", "_layer_info"]

if __name__ == "__main__":
    main()
