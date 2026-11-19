"""Every file this project puts on a PC: where it comes from in the repo, where
it goes, and which machines get it. The installer and `doctor` both read this
list, so what is installed and what is checked can't disagree.

`when`:
  always   every PC with Gaming Mode
  nvidia   only where a screen runs on NVIDIA's driver; anywhere else the file
           is a leftover that still changes how gamescope starts
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
GM = REPO / "gaming-mode"
UNIT_DIR = "~/.config/systemd/user"
DROPIN_DIR = f"{UNIT_DIR}/gamescope-session.service.d"


@dataclass(frozen=True)
class Item:
    src: Path
    dest: str  # "~/..." path on the PC
    when: str = "always"


def _dir(sub: str, dest_dir: str, when: str = "always", pattern: str = "*") -> list[Item]:
    return [
        Item(f, f"{dest_dir}/{f.name}", when)
        for f in sorted((GM / sub).glob(pattern))
        if f.is_file()
    ]


def items() -> list[Item]:
    out: list[Item] = []
    out += _dir("bin", "~/.local/bin")
    out += _dir("test-form", "~/.local/share/gaming-mode/test-form")
    out += _dir("systemd/user", UNIT_DIR, pattern="*.service")
    out.append(Item(GM / "systemd/user/gamescope-session.service.d/easy-switch.conf", f"{DROPIN_DIR}/easy-switch.conf"))
    out.append(Item(GM / "applications/gaming-mode.desktop", "~/Desktop/gaming-mode.desktop"))
    out += _dir("applications", "~/.local/share/applications", pattern="*.desktop")
    out.append(Item(GM / "autostart/easy-switch-restore.desktop", "~/.config/autostart/easy-switch-restore.desktop"))
    # NVIDIA only
    out.append(Item(GM / "nvidia/gamescope-wrapper", "~/.local/share/gaming-mode/bin/gamescope", "nvidia"))
    out.append(Item(GM / "nvidia/gamescope-session-nvidia.conf", f"{DROPIN_DIR}/nvidia.conf", "nvidia"))
    out.append(Item(GM / "nvidia/gamescope-session-delay.conf", f"{DROPIN_DIR}/start-delay.conf", "nvidia"))
    out.append(Item(GM / "nvidia/50-nvidia-tv-fix.lua", "~/.config/gamescope/scripts/50-nvidia-tv-fix.lua", "nvidia"))
    out += _dir("nvidia/bin", "~/.local/bin", "nvidia")
    return out


def rendered(item: Item, home: str) -> str:
    """The file as it should be on the PC (templates carry @HOME@)."""
    return item.src.read_text().replace("@HOME@", home)


USER_UNITS = ["steam.service", "steam-game-performance.service", "easy-switch-hotkeys.service", "gaming-mode-diag.service"]
