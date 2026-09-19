"""
Hardware Telemetry & lm_sensors Capability Yarn for Textile.
Provides high-speed hardware temperature, fan speeds, CPU core frequencies, and thermal metrics.
Layer 10 (Core POSIX).
"""

import ctypes
import ctypes.util
import json
import os
from pathlib import Path
import shutil
import subprocess
from typing import Any, Dict, List, Optional

from textile.core.base import BaseYarn, strand, LAYER_BASE


class SensorsAPI:
    """Hardware Telemetry API powered by libsensors C Library / sensors JSON / sysfs."""

    def __init__(self):
        self._libsensors = None
        self._init_libsensors()

    def _init_libsensors(self):
        lib_path = ctypes.util.find_library("sensors") if hasattr(ctypes, "util") else None
        if not lib_path:
            for candidate in ("libsensors.so.5", "libsensors.so.4", "libsensors.so"):
                try:
                    self._libsensors = ctypes.CDLL(candidate)
                    break
                except Exception:
                    pass
        else:
            try:
                self._libsensors = ctypes.CDLL(lib_path)
            except Exception:
                pass

        if self._libsensors:
            try:
                self._libsensors.sensors_init(None)
            except Exception:
                self._libsensors = None

    def is_available(self) -> bool:
        if self._libsensors or shutil.which("sensors"):
            return True
        return os.path.exists("/sys/class/hwmon")

    def get_sensor_data(self) -> Dict[str, Any]:
        if shutil.which("sensors"):
            try:
                res = subprocess.run(["sensors", "-j"], capture_output=True, text=True, timeout=3)
                raw_out = res.stdout.strip()
                if raw_out:
                    idx = raw_out.find("{")
                    if idx != -1:
                        data = json.loads(raw_out[idx:])
                        return self._format_sensors_json(data)
            except Exception:
                pass
        return self._read_sysfs_hwmon()

    def _format_sensors_json(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        result: Dict[str, Any] = {"cpu": {}, "gpu": {}, "fans": {}, "battery": {}, "other": {}, "raw": raw_data}
        max_cpu_temp = 0.0

        for chip_name, chip_info in raw_data.items():
            if not isinstance(chip_info, dict):
                continue
            for feature, subfeatures in chip_info.items():
                if feature == "Adapter" or not isinstance(subfeatures, dict):
                    continue
                for sub_key, sub_val in subfeatures.items():
                    if not isinstance(sub_val, (int, float)):
                        continue
                    feat_lower = feature.lower()
                    sub_lower = sub_key.lower()

                    if "temp" in sub_lower and "input" in sub_lower:
                        val_c = round(float(sub_val), 1)
                        if "coretemp" in chip_name or "k10temp" in chip_name or "cpu" in feat_lower:
                            result["cpu"][f"{chip_name} {feature}"] = f"{val_c}°C"
                            if val_c > max_cpu_temp:
                                max_cpu_temp = val_c
                        elif "amdgpu" in chip_name or "nouveau" in chip_name or "nvidia" in chip_name:
                            result["gpu"][f"{chip_name} {feature}"] = f"{val_c}°C"
                        else:
                            result["other"][f"{chip_name} {feature}"] = f"{val_c}°C"

                    elif "fan" in sub_lower and "input" in sub_lower:
                        result["fans"][f"{chip_name} {feature}"] = f"{int(sub_val)} RPM"

                    elif "in" in sub_lower and "input" in sub_lower:
                        result["other"][f"{chip_name} {feature} (Voltage)"] = f"{round(float(sub_val), 2)} V"

        if max_cpu_temp > 0:
            result["max_cpu_temp"] = f"{max_cpu_temp}°C"
        return result

    def _read_sysfs_hwmon(self) -> Dict[str, Any]:
        hwmon_path = Path("/sys/class/hwmon")
        if not hwmon_path.exists():
            return {"error": "/sys/class/hwmon not found"}

        data: Dict[str, Any] = {"temperatures": {}, "fans": {}}
        for hw_dir in hwmon_path.glob("hwmon*"):
            name_file = hw_dir / "name"
            name = name_file.read_text().strip() if name_file.exists() else hw_dir.name

            for temp_input in hw_dir.glob("temp*_input"):
                try:
                    temp_c = round(int(temp_input.read_text().strip()) / 1000.0, 1)
                    label_file = hw_dir / temp_input.name.replace("_input", "_label")
                    label = label_file.read_text().strip() if label_file.exists() else temp_input.stem
                    data["temperatures"][f"{name} {label}"] = f"{temp_c}°C"
                except Exception:
                    pass

            for fan_input in hw_dir.glob("fan*_input"):
                try:
                    rpm = int(fan_input.read_text().strip())
                    label_file = hw_dir / fan_input.name.replace("_input", "_label")
                    label = label_file.read_text().strip() if label_file.exists() else fan_input.stem
                    data["fans"][f"{name} {label}"] = f"{rpm} RPM"
                except Exception:
                    pass
        return data

    def get_cpu_frequencies(self) -> List[Dict[str, Any]]:
        cpu_dir = Path("/sys/devices/system/cpu")
        freqs = []
        if not cpu_dir.exists():
            return freqs
        for c_dir in sorted(cpu_dir.glob("cpu[0-9]*")):
            cur_freq_file = c_dir / "cpufreq" / "scaling_cur_freq"
            gov_file = c_dir / "cpufreq" / "scaling_governor"
            if cur_freq_file.exists():
                try:
                    freq_mhz = round(int(cur_freq_file.read_text().strip()) / 1000.0, 1)
                    gov = gov_file.read_text().strip() if gov_file.exists() else "unknown"
                    freqs.append({"core": c_dir.name, "freq": f"{freq_mhz} MHz", "governor": gov})
                except Exception:
                    pass
        return freqs


sensors_api = SensorsAPI()


class Sensors(BaseYarn):
    name = "sensors"
    description = "Hardware Telemetry: Real-Time CPU/GPU Temperatures, Fan Speeds, and Core Frequencies."
    version = "1.0.0"
    layer = LAYER_BASE  # Layer 10

    def is_available(self) -> bool:
        return sensors_api.is_available()

    @strand(description="Retrieve hardware telemetry (temperatures, fans, voltages, power) via lm_sensors / sysfs.")
    def sensors_get_telemetry(self) -> Dict[str, Any]:
        """Retrieve hardware telemetry (temperatures, fans, voltages, power) via lm_sensors / sysfs."""
        return sensors_api.get_sensor_data()

    @strand(description="Retrieve live CPU core frequencies (MHz) and scaling governors across CPU cores.")
    def sensors_get_cpu_freqs(self) -> List[Dict[str, Any]]:
        """Retrieve live CPU core frequencies (MHz) and scaling governors across CPU cores."""
        return sensors_api.get_cpu_frequencies()
