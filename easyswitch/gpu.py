"""Which graphics driver runs each screen connector, read from DRM sysfs.

Everything vendor-specific in this project hangs off `Gpu.vendor`:
  nvidia  NVIDIA's own driver (proprietary or open kernel module)
  amd     amdgpu / radeon (Mesa)
  intel   i915 / xe (Mesa)
  other   anything else (nouveau, virtio ...): treated like Mesa, no extras
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .system import System

DRM = "/sys/class/drm"
VENDORS = {"nvidia": "nvidia", "amdgpu": "amd", "radeon": "amd", "i915": "intel", "xe": "intel"}


@dataclass
class Gpu:
    card: str  # "card1"
    driver: str  # kernel driver name: "nvidia", "amdgpu", ...
    connectors: list[str] = field(default_factory=list)  # "DP-3", "HDMI-A-1"

    @property
    def vendor(self) -> str:
        return VENDORS.get(self.driver, "other")


def detect(sys_: System) -> list[Gpu]:
    names = sys_.listdir(DRM) or []
    gpus = []
    for card in names:
        if not re.fullmatch(r"card\d+", card):
            continue
        driver = sys_.realpath(f"{DRM}/{card}/device/driver").rsplit("/", 1)[-1]
        conns = [
            n.split("-", 1)[1]
            for n in names
            if n.startswith(card + "-") and not n.split("-", 1)[1].startswith("Writeback")
        ]
        gpus.append(Gpu(card, driver, conns))
    return gpus


def for_connector(gpus: list[Gpu], connector: str) -> Gpu | None:
    return next((g for g in gpus if connector in g.connectors), None)


def vendors(gpus: list[Gpu]) -> set[str]:
    return {g.vendor for g in gpus}


def nvidia_version(sys_: System) -> str | None:
    text = sys_.read("/proc/driver/nvidia/version") or ""
    m = re.search(r"\b(\d{3}\.\d+(?:\.\d+)?)\b", text)
    return m.group(1) if m else None
