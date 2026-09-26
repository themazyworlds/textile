"""
Multimodal Screen Vision & Visual Snapshot Capability Yarn.
Supports native Wayland (grim) and cross-platform screen capture with automatic JPEG compression.
Layer 10 (Core POSIX).
"""

import contextlib
import io
import shutil
import subprocess

try:
    import mss
except (ImportError, AttributeError, OSError):
    mss = None

try:
    from PIL import Image
except (ImportError, AttributeError, OSError):
    Image = None

from textile.core.base import Yarn, strand


class ScreenVisionEngine:
    def __init__(self):
        self._grim_bin = shutil.which("grim")
        self._has_grim = self._grim_bin is not None
        self._sct = None

    def _get_sct(self):
        if self._sct is None and mss is not None:
            with contextlib.suppress(AttributeError, TypeError, OSError):
                self._sct = mss.MSS() if hasattr(mss, "MSS") else mss.mss()
        return self._sct

    def capture_jpeg(self, max_dimension: int = 1280, quality: int = 70) -> bytes | None:
        if Image is None:
            return None

        if self._has_grim and self._grim_bin:
            with contextlib.suppress(OSError, AttributeError, TypeError, ValueError, subprocess.SubprocessError):
                res = subprocess.run(
                    [self._grim_bin, "-t", "jpeg", "-q", "75", "-"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    timeout=1.0,
                    check=False,
                )
                if res.returncode == 0 and res.stdout:
                    img = Image.open(io.BytesIO(res.stdout))
                    img.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)
                    out = io.BytesIO()
                    img.save(out, format="JPEG", quality=quality)
                    return out.getvalue()

        sct = self._get_sct()
        if sct is not None:
            with contextlib.suppress(AttributeError, TypeError, ValueError, OSError):
                monitor = sct.monitors[0]
                sct_img = sct.grab(monitor)
                img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
                img.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)
                out = io.BytesIO()
                img.save(out, format="JPEG", quality=quality)
                return out.getvalue()

        return None


vision_engine = ScreenVisionEngine()


class ScreenVision(Yarn):
    def is_available(self) -> bool:
        return True

    @strand()
    def capture_screen(self, purpose: str | None = None) -> str:
        """Capture a high-resolution screenshot snapshot of the active screen and windows.

        :param purpose: Optional reason for capturing screen.
        """
        jpeg_bytes = vision_engine.capture_jpeg(max_dimension=1280, quality=75)
        if jpeg_bytes:
            return f"[Screen captured ({len(jpeg_bytes)} bytes). Reason: {purpose or 'user query'}]"
        return "Error: Could not capture screen frame on this system."
