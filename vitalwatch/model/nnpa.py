"""Detect the IBM Telum on-chip AI accelerator (NNPA) and the libraries that use it.

Never raises: every probe reports what it found, so the dashboard and the
benchmark can say honestly whether inference ran on the accelerator.
"""

from __future__ import annotations

import ctypes.util
import glob
import importlib.metadata as md
import os
import platform
import sys


def _cpuinfo() -> dict:
    info = {"features": [], "machine_type": None}
    try:
        with open("/proc/cpuinfo", encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except OSError:
        return info
    for line in text.splitlines():
        low = line.lower()
        if low.startswith("features") and ":" in line:
            info["features"] = line.split(":", 1)[1].split()
        elif "machine =" in low and info["machine_type"] is None:
            # s390x: "processor 0: version = 00,  identification = ..., machine = 3931"
            info["machine_type"] = low.split("machine =", 1)[1].strip().split()[0]
    return info


# IBM machine type codes -> family names (best effort, for display only;
# the raw machine type is always reported alongside).
MACHINE_NAMES = {
    "8561": "IBM z15 / LinuxONE III (no NNPA)", "8562": "IBM z15 / LinuxONE III (no NNPA)",
    "3931": "IBM z16 / LinuxONE 4 (Telum)", "3932": "IBM z16 / LinuxONE 4 (Telum)",
    "9175": "IBM z17 / LinuxONE 5 (Telum II)",
}


def _find_zdnn() -> str | None:
    override = os.environ.get("SNAPML_ZDNN_LIB")
    if override and os.path.exists(override):
        return override
    lib = ctypes.util.find_library("zdnn")
    if lib:
        return lib
    patterns = [
        "/usr/lib*/libzdnn.so*", "/usr/lib/*/libzdnn.so*", "/usr/local/lib*/libzdnn.so*",
        sys.prefix + "/lib/python3*/site-packages/**/libzdnn*.so*",
    ]
    for pat in patterns:
        hits = glob.glob(pat, recursive=True)
        if hits:
            return sorted(hits)[0]
    return None


def _version(pkg: str) -> str | None:
    try:
        return md.version(pkg)
    except md.PackageNotFoundError:
        return None


def detect_nnpa() -> dict:
    """Return a JSON-serialisable description of the AI acceleration available."""
    cpu = _cpuinfo()
    machine = platform.machine()
    result = {
        "arch": machine,
        "byteorder": sys.byteorder,
        "is_ibm_z": machine == "s390x",
        "machine_type": cpu["machine_type"],
        "machine_name": MACHINE_NAMES.get(cpu["machine_type"] or "", None),
        "cpu_has_nnpa": "nnpa" in cpu["features"],
        "zdnn_library": _find_zdnn(),
        "snapml": _version("snapml"),
        "ibm_zdnn_plugin": _version("ibm-zdnn-plugin"),
        "tensorflow": _version("tensorflow"),
        "llama_cpp_python": _version("llama_cpp_python") or _version("llama-cpp-python"),
    }
    result["nnpa_usable"] = bool(result["cpu_has_nnpa"] and result["zdnn_library"])
    return result
