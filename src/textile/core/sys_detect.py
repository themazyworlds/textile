"""
Textile OS Environment & System Command Detection Helpers.
"""

import os


def detect_terminal() -> str:
    """Detect available terminal emulator from $TERMINAL / $TERM environment variables."""
    return os.environ.get("TERMINAL") or os.environ.get("TERM") or "xterm"


def detect_shell() -> str:
    """Detect default shell executable from $SHELL or fallback to /bin/bash."""
    return os.environ.get("SHELL") or "/bin/bash"


def detect_terminal_and_shell() -> tuple[str, str]:
    """Resolve preferred desktop terminal emulator and active shell."""
    return detect_terminal(), detect_shell()
