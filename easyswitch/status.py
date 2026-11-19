"""`easy-switch status` and `easy-switch commands`: what this PC is doing and
what it can be asked to do, as JSON for other programs (Home Assistant).

Both are read-only and work over plain SSH: they read sysfs, the config and the
state files, never the desktop session.
"""

from __future__ import annotations

import argparse
import json
import tomllib

from . import gpu as gpumod
from .system import System

CONFIG = "~/.config/easy-switch/config.toml"


def _modes(sys_: System) -> dict:
    try:
        return tomllib.loads(sys_.read(CONFIG) or "").get("modes", {})
    except tomllib.TOMLDecodeError:
        return {}


def _primary(mode: dict) -> str | None:
    return next((o for o, c in mode.get("outputs", {}).items() if c.get("enable") and c.get("primary")), None)


def _enabled(sys_: System, gpus, connector: str) -> bool:
    g = gpumod.for_connector(gpus, connector)
    return bool(g) and (sys_.read(f"{gpumod.DRM}/{g.card}-{connector}/enabled") or "").strip() == "enabled"


def active_mode(sys_: System, gpus, modes: dict) -> str | None:
    """The mode whose primary screen is on and whose disabled screens are off."""
    for name, m in modes.items():
        prim = _primary(m)
        if not prim or not _enabled(sys_, gpus, prim):
            continue
        if any(_enabled(sys_, gpus, o) for o, c in m.get("outputs", {}).items() if c.get("enable") is False):
            continue
        return name
    return None


def status(sys_: System) -> dict:
    gpus = gpumod.detect(sys_)
    modes = _modes(sys_)
    _, uid = sys_.cmd("id", "-u")
    runtime = f"/run/user/{uid.strip()}"
    gaming = sys_.exists(f"{runtime}/gamescope-environment")
    rc, _ = sys_.cmd("pgrep", "-f", "reaper SteamLaunch AppId=")
    _, host = sys_.cmd("uname", "-n")
    return {
        "host": host.strip().split(".")[0],
        "session": "gaming" if gaming else "desktop",
        "mode": active_mode(sys_, gpus, modes),
        "remembered_mode": (sys_.read("~/.local/state/easy-switch/last-mode") or "").strip() or None,
        "modes": {n: m.get("description", "") for n, m in modes.items()},
        "game_running": rc == 0,
        "screens_on": sorted(c for g in gpus for c in g.connectors if _enabled(sys_, gpus, c)),
        "gpu": sorted(gpumod.vendors(gpus)),
    }


def commands(sys_: System) -> list[dict]:
    """Everything another program may ask this PC to do. `run` is the argument
    list after `easy-switch`."""
    modes = _modes(sys_)
    out = [
        {
            "id": "switch",
            "label": "Switch mode",
            "kind": "select",
            "options": list(modes),
            "state": "mode",
            "run": ["{option}"],
        },
    ]
    if any(m.get("gamescope_output") for m in modes.values()):
        out.append(
            {
                "id": "restart_gaming_mode",
                "label": "Restart Gaming Mode",
                "kind": "button",
                "available": "session == gaming",
                "run": ["--restart-gaming-mode"],
            }
        )
    return out


def main(which: str, argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog=f"easy-switch {which}")
    p.add_argument("--json", action="store_true", help="JSON (the default output is JSON too, for now)")
    p.parse_args(argv)
    sys_ = System()
    print(json.dumps(status(sys_) if which == "status" else commands(sys_), indent=1))
    return 0
