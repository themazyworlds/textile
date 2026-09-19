"""
Multimodal Screen Vision & Visual Snapshot Capability Yarn.
Supports native Wayland (grim) and cross-platform screen capture with automatic JPEG compression.
Layer 10 (Core POSIX).
"""

import io
import shutil
import subprocess
from typing import Any, Dict, List, Optional

from textile.core.base import BaseYarn, strand, LAYER_BASE


class ScreenVisionEngine:
    def __init__(self):
        self._has_grim = shutil.which("grim") is not None
        self._sct = None

    def _get_sct(self):
        if self._sct is None:
            try:
                import mss
                self._sct = mss.MSS() if hasattr(mss, "MSS") else mss.mss()
            except Exception:
                self._sct = None
        return self._sct

    def capture_jpeg(self, max_dimension: int = 1280, quality: int = 70) -> Optional[bytes]:
        from PIL import Image

        if self._has_grim:
            try:
                res = subprocess.run(
                    ["grim", "-t", "jpeg", "-q", "75", "-"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    timeout=1.0,
                )
                if res.returncode == 0 and res.stdout:
                    img = Image.open(io.BytesIO(res.stdout))
                    img.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)
                    out = io.BytesIO()
                    img.save(out, format="JPEG", quality=quality)
                    return out.getvalue()
            except Exception:
                pass

        sct = self._get_sct()
        if sct is not None:
            try:
                monitor = sct.monitors[0]
                sct_img = sct.grab(monitor)
                img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
                img.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)
                out = io.BytesIO()
                img.save(out, format="JPEG", quality=quality)
                return out.getvalue()
            except Exception:
                pass

        return None


vision_engine = ScreenVisionEngine()


class ScreenVision(BaseYarn):
    name = "screen_vision"
    description = "Multimodal Screen Frame Capture Provider."
    version = "1.0.0"
    layer = LAYER_BASE  # Layer 10

    def is_available(self) -> bool:
        return True

    @strand(description="Capture a high-resolution screenshot snapshot of the active screen and windows.")
    def capture_screen(self, purpose: Optional[str] = None) -> str:
        """Capture a high-resolution screenshot snapshot of the active screen and windows.

        :param purpose: Optional reason for capturing screen.
        """
        jpeg_bytes = vision_engine.capture_jpeg(max_dimension=1280, quality=75)
        if jpeg_bytes:
            return f"[Screen captured ({len(jpeg_bytes)} bytes). Reason: {purpose or 'user query'}]"
        return "Error: Could not capture screen frame on this system."
