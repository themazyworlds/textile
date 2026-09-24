"""
Textile Main CLI Entry Point.
Routes to Typer CLI Application.
"""

from textile.core.cli_typer import app


def main():
    app()

if __name__ == "__main__":
    main()
