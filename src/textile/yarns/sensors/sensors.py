"""
Hardware Telemetry & lm_sensors Capability Yarn for Textile.
Provides high-speed hardware temperature, fan speeds, CPU core frequencies, and thermal metrics.
Layer 10 (Core POSIX).
"""

import contextlib
import ctypes
import ctypes.util
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import psutil

from textile.core.base import CapabilityTier, Yarn, strand


class SensorsAPI:
    """Hardware Telemetry API powered by libsensors C Library / sensors JSON / psutil / sysfs."""

    def __init__(self):
        self._libsensors = None
        self._init_libsensors()

    def _init_libsensors(self):
        lib_path = ctypes.util.find_library("sensors") if hasattr(ctypes, "util") else None
        if not lib_path:
            for candidate in ("libsensors.so.5", "libsensors.so.4", "libsensors.so"):
                with contextlib.suppress(OSError, AttributeError):
                    self._libsensors = ctypes.CDLL(candidate)
                    break
        else:
            with contextlib.suppress(OSError, AttributeError):
                self._libsensors = ctypes.CDLL(lib_path)

        if self._libsensors:
            with contextlib.suppress(AttributeError, TypeError, OSError):
                self._libsensors.sensors_init(None)

    def is_available(self) -> bool:
        if self._libsensors or shutil.which("sensors"):
            return True
        return os.path.exists("/sys/class/hwmon") or os.path.exists("/sys/class/thermal")

    def get_sensor_data(self) -> dict[str, Any]:
        sensors_bin = shutil.which("sensors")
        if sensors_bin:
            with contextlib.suppress(OSError, ValueError, TypeError, json.JSONDecodeError, subprocess.SubprocessError):
                res = subprocess.run([sensors_bin, "-j"], capture_output=True, text=True, timeout=3, check=False)
                raw_out = res.stdout.strip()
                if raw_out:
                    idx = raw_out.find("{")
                    if idx != -1:
                        data = json.loads(raw_out[idx:])
                        res_dict = self._format_sensors_json(data)
                        if res_dict and (res_dict.get("cpu") or res_dict.get("other") or res_dict.get("fans")):
                            return res_dict

        # Fallback to psutil
        with contextlib.suppress(Exception):
            p_data: dict[str, Any] = {"cpu": {}, "gpu": {}, "fans": {}, "battery": {}, "other": {}}
            temps = psutil.sensors_temperatures()
            if temps:
                max_cpu = 0.0
                for name, entries in temps.items():
                    for entry in entries:
                        label = entry.label or name
                        val_c = round(entry.current, 1)
                        name_lower = name.lower()
                        if "coretemp" in name_lower or "k10temp" in name_lower or "cpu" in name_lower:
                            p_data["cpu"][f"{name} {label}".strip()] = f"{val_c}°C"
                            max_cpu = max(max_cpu, val_c)
                        elif "gpu" in name_lower or "nvidia" in name_lower or "amdgpu" in name_lower:
                            p_data["gpu"][f"{name} {label}".strip()] = f"{val_c}°C"
                        else:
                            p_data["other"][f"{name} {label}".strip()] = f"{val_c}°C"
                if max_cpu > 0:
                    p_data["max_cpu_temp"] = f"{max_cpu}°C"

            fans = psutil.sensors_fans()
            if fans:
                for name, entries in fans.items():
                    for entry in entries:
                        label = entry.label or name
                        p_data["fans"][f"{name} {label}".strip()] = f"{int(entry.current)} RPM"

            batt = psutil.sensors_battery()
            if batt:
                p_data["battery"] = {"percent": f"{round(batt.percent, 1)}%", "plugged": batt.power_plugged}

            if p_data["cpu"] or p_data["fans"] or p_data["battery"] or p_data["other"]:
                return p_data

        return self._read_sysfs_hwmon()

    def _format_sensors_json(self, raw_data: dict[str, Any]) -> dict[str, Any]:
        result: dict[str, Any] = {"cpu": {}, "gpu": {}, "fans": {}, "battery": {}, "other": {}, "raw": raw_data}
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
                            max_cpu_temp = max(max_cpu_temp, val_c)
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

    def _read_sysfs_hwmon(self) -> dict[str, Any]:
        hwmon_path = Path("/sys/class/hwmon")
        if not hwmon_path.exists():
            return {"error": "/sys/class/hwmon not found"}

        data: dict[str, Any] = {"temperatures": {}, "fans": {}}
        for hw_dir in hwmon_path.glob("hwmon*"):
            name_file = hw_dir / "name"
            name = name_file.read_text().strip() if name_file.exists() else hw_dir.name

            for temp_input in hw_dir.glob("temp*_input"):
                with contextlib.suppress(OSError, ValueError, TypeError):
                    temp_c = round(int(temp_input.read_text().strip()) / 1000.0, 1)
                    label_file = hw_dir / temp_input.name.replace("_input", "_label")
                    label = label_file.read_text().strip() if label_file.exists() else temp_input.stem
                    data["temperatures"][f"{name} {label}"] = f"{temp_c}°C"

            for fan_input in hw_dir.glob("fan*_input"):
                with contextlib.suppress(OSError, ValueError, TypeError):
                    rpm = int(fan_input.read_text().strip())
                    label_file = hw_dir / fan_input.name.replace("_input", "_label")
                    label = label_file.read_text().strip() if label_file.exists() else fan_input.stem
                    data["fans"][f"{name} {label}"] = f"{rpm} RPM"
        return data

    def get_cpu_frequencies(self) -> list[dict[str, Any]]:
        cpu_dir = Path("/sys/devices/system/cpu")
        freqs = []
        if cpu_dir.exists():
            for c_dir in sorted(cpu_dir.glob("cpu[0-9]*")):
                cur_freq_file = c_dir / "cpufreq" / "scaling_cur_freq"
                gov_file = c_dir / "cpufreq" / "scaling_governor"
                if cur_freq_file.exists():
                    with contextlib.suppress(OSError, ValueError, TypeError):
                        freq_mhz = round(int(cur_freq_file.read_text().strip()) / 1000.0, 1)
                        gov = gov_file.read_text().strip() if gov_file.exists() else "unknown"
                        freqs.append({"core": c_dir.name, "freq": f"{freq_mhz} MHz", "governor": gov})

        if not freqs:
            with contextlib.suppress(Exception):
                p_freqs = psutil.cpu_freq(percpu=True)
                if p_freqs:
                    for i, pf in enumerate(p_freqs):
                        freqs.append({
                            "core": f"cpu{i}",
                            "freq": f"{round(pf.current, 1)} MHz",
                            "governor": "unknown",
                        })

        return freqs


sensors_api = SensorsAPI()


class Sensors(Yarn):
    def is_available(self) -> bool:
        return sensors_api.is_available()

    @strand(
        description="Retrieve hardware telemetry (temperatures, fans, voltages, power) via lm_sensors / sysfs.",
        tier=CapabilityTier.OBSERVE,
    )
    def sensors_get_telemetry(self) -> dict[str, Any]:
        """Retrieve hardware telemetry (temperatures, fans, voltages, power) via lm_sensors / sysfs."""
        return sensors_api.get_sensor_data()

    @strand(
        description="Retrieve live CPU core frequencies (MHz) and scaling governors across CPU cores.",
        tier=CapabilityTier.OBSERVE,
    )
    def sensors_get_cpu_freqs(self) -> list[dict[str, Any]]:
        """Retrieve live CPU core frequencies (MHz) and scaling governors across CPU cores."""
        return sensors_api.get_cpu_frequencies()
