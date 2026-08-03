"""GPU auto-detection and configuration."""

import os
import subprocess
from dataclasses import dataclass
from typing import Optional

from .ui import run_cmd


@dataclass
class GPUInfo:
    vendor: str
    model: str
    driver: str
    mesa_config: dict


# ── GPU Configs ────────────────────────────────────────────

GPU_CONFIGS = {
    "turnip": {
        "GALLIUM_DRIVER": "zink",
        "MESA_GL_VERSION_OVERRIDE": "4.6",
        "MESA_GLES_VERSION_OVERRIDE": "3.2",
        "ZINK_DESCRIPTORS": "lazy",
    },
    "panfrost": {
        "GALLIUM_DRIVER": "panfrost",
        "MESA_GL_VERSION_OVERRIDE": "4.6",
    },
    "virpipe": {
        "GALLIUM_DRIVER": "virpipe",
        "MESA_GL_VERSION_OVERRIDE": "4.1",
        "MESA_GLES_VERSION_OVERRIDE": "3.1",
    },
    "software": {
        "LIBGL_ALWAYS_SOFTWARE": "1",
    },
}


def detect_gpu() -> GPUInfo:
    """Auto-detect GPU via Android system properties."""
    egl = _get_prop("ro.hardware.egl")
    board = _get_prop("ro.product.board")
    chipname = _get_prop("ro.hardware.chipname")
    brand = _get_prop("ro.product.brand")
    hw = _get_prop("ro.hardware")
    soc = _get_prop("ro.soc.model")
    platform = _get_prop("ro.board.platform")
    props = (egl + board + chipname + brand + hw + soc + platform).lower()

    # Qualcomm Adreno detection
    if any(x in props for x in ["qualcomm", "adreno", "qcom"]):
        return GPUInfo(
            vendor="Qualcomm",
            model=_get_gpu_model("Adreno"),
            driver="turnip",
            mesa_config=GPU_CONFIGS["turnip"],
        )

    # Samsung Exynos (AMD RDNA / Xclipse) detection
    if any(x in props for x in ["exynos"]) or ("samsung" in props and any(x in props for x in ["s5e9", "erd9"])):
        return GPUInfo(
            vendor="Samsung",
            model=_get_gpu_model("Exynos"),
            driver="virpipe",
            mesa_config=GPU_CONFIGS["virpipe"],
        )

    # ARM Mali detection
    if any(x in props for x in ["mali", "arm"]):
        return GPUInfo(
            vendor="ARM",
            model=_get_gpu_model("Mali"),
            driver="panfrost",
            mesa_config=GPU_CONFIGS["panfrost"],
        )

    # Virgl (proot environment)
    if _has_virgl():
        return GPUInfo(
            vendor="Virgl",
            model="virglrenderer",
            driver="virpipe",
            mesa_config=GPU_CONFIGS["virpipe"],
        )

    # Fallback to software rendering
    return GPUInfo(
        vendor="Unknown",
        model="Software",
        driver="software",
        mesa_config=GPU_CONFIGS["software"],
    )


def _get_prop(prop: str) -> str:
    """Get Android system property."""
    try:
        result = subprocess.run(
            ["getprop", prop],
            capture_output=True, text=True, timeout=5
        )
        return result.stdout.strip()
    except Exception:
        return ""


def _get_gpu_model(prefix: str) -> str:
    """Try to get specific GPU model name."""
    # Common Adreno models
    for model in ["A660", "A740", "A730", "A715", "A710", "A650", "A640", "A630"]:
        if model.lower() in (_get_prop("ro.hardware.chipname") + _get_prop("ro.product.board")).lower():
            return f"{prefix} {model}"
    return prefix


def _has_virgl() -> bool:
    """Check if virglrenderer is available."""
    rc, _ = run_cmd("command -v virgl_test_server_android")
    return rc == 0


def write_gpu_config(gpu: GPUInfo, path: Optional[str] = None):
    """Write GPU config to file."""
    if path is None:
        path = os.path.expanduser("~/.config/gpu.conf")

    os.makedirs(os.path.dirname(path), exist_ok=True)

    with open(path, "w") as f:
        f.write(f"# arinanoLabs GPU Configuration\n")
        f.write(f"# Detected: {gpu.vendor} {gpu.model} ({gpu.driver})\n\n")
        for key, value in gpu.mesa_config.items():
            f.write(f"export {key}={value}\n")

    return path


def get_gpu_summary(gpu: GPUInfo) -> str:
    """Get human-readable GPU summary."""
    mode = "Hardware accelerated" if gpu.driver != "software" else "Software fallback"
    return f"{gpu.vendor} {gpu.model} ({gpu.driver}) — {mode}"
