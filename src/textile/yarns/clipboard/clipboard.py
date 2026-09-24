"""
Universal Cross-Desktop Clipboard Capability Yarn for Textile via Native pyxclip.
Provides high-performance, non-blocking text clipboard reading, writing, and clearing
across Wayland and X11 compositors without external CLI subprocesses.
Layer 50 (Desktop Protocol).
"""

import logging
import os

try:
    import pyxclip
except (ImportError, AttributeError, OSError):
    pyxclip = None

from textile.core.base import CapabilityTier, Yarn, strand

logger = logging.getLogger(__name__)


class Clipboard(Yarn):
    """Universal System Clipboard Capability Yarn via Native pyxclip."""

    def is_available(self) -> bool:
        if pyxclip is None:
            return False
        return bool(os.environ.get("WAYLAND_DISPLAY") or os.environ.get("DISPLAY"))

    @strand(description="Read the current text content from the system clipboard.", tier=CapabilityTier.OBSERVE)
    def clipboard_get(self) -> str:
        """Read and return text from the system clipboard."""
        if pyxclip is None:
            return "Error: 'pyxclip' module is not installed."
        try:
            val = pyxclip.paste()
            return str(val) if val else ""
        except (AttributeError, OSError, RuntimeError, ValueError, TypeError) as e:
            if "empty" in str(e).lower():
                return ""
            return f"Error reading clipboard: {e}"

    @strand(description="Copy text content into the system clipboard.", tier=CapabilityTier.INTERACT)
    def clipboard_set(self, text: str) -> str:
        """Write text to the system clipboard.

        :param text: Text string to copy to the clipboard.
        """
        if pyxclip is None:
            return "Error: 'pyxclip' module is not installed."
        try:
            pyxclip.copy(text)
            return f"Successfully copied {len(text)} characters to clipboard."
        except (AttributeError, OSError, RuntimeError, ValueError, TypeError) as e:
            return f"Error writing to clipboard: {e}"

    @strand(description="Clear all content from the system clipboard.", tier=CapabilityTier.INTERACT)
    def clipboard_clear(self) -> str:
        """Clear the system clipboard."""
        if pyxclip is None:
            return "Error: 'pyxclip' module is not installed."
        try:
            pyxclip.clear()
            return "Clipboard cleared successfully."
        except (AttributeError, OSError, RuntimeError, ValueError, TypeError) as e:
            return f"Error clearing clipboard: {e}"
