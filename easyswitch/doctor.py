"""`easy-switch doctor`: is this PC set up the way the project expects?

Read-only. Every check returns ok / warn / fail / skip with one line of what was
found and, when something is wrong, how to put it right. Exit code 1 when any
check failed.
"""

from __future__ import annotations

import argparse
import json
import re
import tomllib
from dataclasses import asdict, dataclass

from . import gpu as gpumod
from . import manifest
from .system import Recorder, System

OK, WARN, FAIL, SKIP = "ok", "warn", "fail", "skip"
CONFIG = "~/.config/easy-switch/config.toml"
MANGOHUD = "~/.config/MangoHud"
HOTKEY_RE = re.compile(r"^((ctrl|alt|shift|meta)\+)*[a-z0-9]+$")

# environment.d variables that only do something on one vendor's driver
VENDOR_VARS = {
    "nvidia": ("__GL_", "PROTON_DLSS", "PROTON_NVIDIA", "__NV_"),
    "amd": ("PROTON_FSR4", "ENABLE_LAYER_MESA_ANTI_LAG", "RADV_", "AMD_"),
}


@dataclass
class Result:
    group: str
    name: str
    status: str
    detail: str = ""
    fix: str = ""


class Doctor:
    def __init__(self, sys_: System) -> None:
        self.sys = sys_
        self.results: list[Result] = []
        self.group = ""
        self.gpus = gpumod.detect(sys_)
        self.vendors = gpumod.vendors(self.gpus)
        self.config: dict | None = None

    def add(self, name: str, status: str, detail: str = "", fix: str = "") -> None:
        self.results.append(Result(self.group, name, status, detail, fix))

    def pkg(self, name: str) -> str | None:
        """Installed version, or None. Also matches packages that provide `name`."""
        rc, out = self.sys.cmd("pacman", "-Q", name)
        return out.strip() if rc == 0 else None

    # ------------------------------------------------------------------ checks

    def check_gpu(self) -> None:
        self.group = "Graphics"
        if not self.gpus:
            self.add("graphics card", FAIL, "no DRM card found in /sys/class/drm")
            return
        for g in self.gpus:
            extra = ""
            if g.vendor == "nvidia":
                extra = f", driver {gpumod.nvidia_version(self.sys) or 'version unknown'}"
            self.add(g.card, OK, f"{g.vendor} ({g.driver}{extra}); connectors: {', '.join(g.connectors) or 'none'}")

    def check_config(self) -> None:
        self.group = "Modes"
        text = self.sys.read(CONFIG)
        if text is None:
            self.add("config", FAIL, f"no {CONFIG}", "arrange the screens, then: easy-switch add <name>")
            return
        try:
            self.config = tomllib.loads(text)
        except tomllib.TOMLDecodeError as e:
            self.add("config", FAIL, f"{CONFIG} does not parse: {e}")
            return
        modes = self.config.get("modes", {})
        if not modes:
            self.add("config", FAIL, "no modes defined", "easy-switch add <name>")
            return
        connectors = {c for g in self.gpus for c in g.connectors}
        _, sinks = self.sys.cmd("pactl", "list", "sinks", "short")
        _, cards = self.sys.cmd("pactl", "list", "cards", "short")
        sink_names = {ln.split("\t")[1] for ln in sinks.splitlines() if "\t" in ln}
        card_names = {ln.split("\t")[1] for ln in cards.splitlines() if "\t" in ln}
        seen_hotkeys: dict[str, str] = {}
        for name, m in modes.items():
            problems, notes = [], []
            named = set(m.get("outputs", {})) | set(m.get("requires_any", []))
            if m.get("gamescope_output"):
                named.add(m["gamescope_output"])
            unknown = sorted(named - connectors)
            if unknown:
                problems.append(f"no such connector on this PC: {', '.join(unknown)}")
            prof = m.get("mangohud")
            if prof and not self.sys.exists(prof if prof.startswith("/") else f"{MANGOHUD}/{prof}"):
                problems.append(f"MangoHud profile {prof} is missing")
            hk = m.get("hotkey")
            if hk:
                if not HOTKEY_RE.match(hk.lower()):
                    problems.append(f"hotkey {hk!r} is not in the form ctrl+alt+down")
                elif hk.lower() in seen_hotkeys:
                    problems.append(f"hotkey {hk} is also used by mode {seen_hotkeys[hk.lower()]}")
                seen_hotkeys[hk.lower()] = name
            sink = m.get("audio")
            if sink and sink not in sink_names:
                card = _sink_card(sink)
                if card and card in card_names:
                    notes.append("sound output is created when the mode is applied (card profile switch)")
                else:
                    notes.append(f"sound device is not there right now ({sink}): off, unplugged or renamed")
            if problems:
                self.add(f"mode {name}", FAIL, "; ".join(problems), f"edit {CONFIG}")
            elif notes:
                self.add(f"mode {name}", WARN if "not there" in notes[0] else OK, "; ".join(notes))
            else:
                self.add(f"mode {name}", OK)
        last = (self.sys.read("~/.local/state/easy-switch/last-mode") or "").strip()
        if last and last not in modes:
            self.add("remembered mode", WARN, f"'{last}' is not a mode any more", "apply any mode once")
        link = self.sys.readlink(f"{MANGOHUD}/MangoHud.conf")
        if any(m.get("mangohud") for m in modes.values()):
            if link is None and self.sys.exists(f"{MANGOHUD}/MangoHud.conf"):
                self.add("MangoHud.conf", FAIL, "is a regular file, so modes can't switch the profile",
                         f"move it to {MANGOHUD}/<mode>.conf and apply a mode")
            elif link is None:
                self.add("MangoHud.conf", WARN, "not set yet", "apply any mode once")
            else:
                self.add("MangoHud.conf", OK, f"-> {link.rsplit('/', 1)[-1]}")

    def gaming_mode_wanted(self) -> bool:
        modes = (self.config or {}).get("modes", {})
        return any(m.get("gamescope_output") for m in modes.values()) or bool(self.pkg("gamescope-session-cachyos"))

    def check_packages(self) -> None:
        self.group = "Packages"
        rc, _ = self.sys.cmd("pacman", "-V")
        if rc == 127:
            self.add("packages", SKIP, "no pacman here: package checks are for Arch-based systems")
            return
        need = {
            "gamescope-session-cachyos": "the Gaming Mode session",
            "gamescope": "the compositor Gaming Mode runs in",
            "python-evdev": "hotkeys inside Gaming Mode",
            "power-profiles-daemon": "performance profile while a game runs",
            "mangohud": "per-mode FPS caps",
            "steam": "",
        }
        for p, why in need.items():
            v = self.pkg(p)
            if v:
                self.add(p, OK, v)
            else:
                self.add(p, FAIL, f"not installed ({why})" if why else "not installed", f"sudo pacman -S {p}")
        if "nvidia" in self.vendors:
            v = self.pkg("gamescope-gbm-git")
            if v:
                self.add("NVIDIA gamescope build", OK, v)
            else:
                self.add("NVIDIA gamescope build", WARN,
                         "stock gamescope on NVIDIA: a 4K screen is corrupted on about half the starts",
                         "cd gaming-mode/nvidia/gamescope-gbm-git && ./update.sh")

    def check_files(self) -> None:
        self.group = "Installed files"
        link = self.sys.readlink("~/.local/bin/easy-switch")
        if link is None:
            self.add("easy-switch command", FAIL, "~/.local/bin/easy-switch is not a link to the repo", "./install.sh")
        else:
            self.add("easy-switch command", OK, f"-> {link}")
        nvidia = "nvidia" in self.vendors
        missing, drift, stale, good = [], [], [], 0
        for it in manifest.items():
            have = self.sys.read(it.dest)
            wanted = it.when == "always" or nvidia
            if not wanted:
                if have is not None:
                    stale.append(it.dest)
                continue
            if have is None:
                missing.append(it.dest)
            elif have != manifest.rendered(it, self.sys.home):
                drift.append(it.dest)
            else:
                good += 1
        fix = "gaming-mode/install.sh"
        if missing:
            self.add("missing", FAIL, ", ".join(missing), fix)
        if drift:
            self.add("differs from the repo", FAIL, ", ".join(drift), f"{fix} (keeps a .pre-gaming-mode backup)")
        if stale:
            self.add("NVIDIA-only leftovers", FAIL,
                     "no screen runs on NVIDIA here, but these still change how gamescope starts: " + ", ".join(stale),
                     "delete them, then: systemctl --user daemon-reload")
        if not (missing or drift or stale):
            self.add("files", OK, f"{good} files match the repo")
        for name in (self.config or {}).get("modes", {}):
            d = f"~/.local/share/applications/easy-switch-{name}.desktop"
            if not self.sys.exists(d):
                self.add(f"launcher for {name}", WARN, f"{d} missing (Steam 'Switch to {name}' entry)", fix)

    def check_units(self) -> None:
        self.group = "Services"
        for u in manifest.USER_UNITS:
            _, out = self.sys.cmd("systemctl", "--user", "is-enabled", u)
            state = out.strip().splitlines()[0] if out.strip() else "unknown"
            if state == "enabled":
                self.add(u, OK, "enabled")
            else:
                self.add(u, FAIL, state, f"systemctl --user enable {u}")
        _, out = self.sys.cmd("systemctl", "--user", "is-enabled", "cachyos-gamescope-autologin.service")
        state = out.strip().splitlines()[0] if out.strip() else "unknown"
        if state in ("masked", "not-found") or "No such file" in out:
            self.add("CachyOS autologin re-arm", OK, state)
        else:
            self.add("CachyOS autologin re-arm", FAIL,
                     f"{state}: every desktop login would point the next login at Gaming Mode",
                     "systemctl --user mask cachyos-gamescope-autologin.service")
        _, groups = self.sys.cmd("id", "-nG")
        if "input" in groups.split():
            self.add("input group", OK)
        else:
            self.add("input group", FAIL, "hotkeys inside Gaming Mode can't read the keyboard",
                     "sudo usermod -aG input $USER, then log out and in")

    def check_steam(self) -> None:
        self.group = "Steam"
        if self.sys.exists("~/.config/inhibit-short-session-tracker"):
            self.add("auto-reset switch", OK, "Gaming Mode won't reset Steam after short sessions")
        else:
            self.add("auto-reset switch", FAIL, "~/.config/inhibit-short-session-tracker missing",
                     "touch ~/.config/inhibit-short-session-tracker")
        beta = self.sys.read("~/.local/share/Steam/package/beta")
        if beta is not None and beta.strip() == "publicbeta":
            self.add("client channel", FAIL,
                     "desktop beta channel: desktop and Gaming Mode re-download the client on every switch",
                     "gaming-mode/install.sh (sets steamdeck_publicbeta)")
        else:
            self.add("client channel", OK, (beta or "stable").strip() or "stable")
        desk = self.sys.read("~/.local/share/applications/steam.desktop")
        if desk is None or "-steamdeck" not in desk:
            self.add("desktop Steam launcher", FAIL, "does not start Steam with -steamdeck", "gaming-mode/install.sh")
        else:
            self.add("desktop Steam launcher", OK, "-steamdeck")
        auto = [f for f in (self.sys.listdir("~/.config/autostart") or []) if re.fullmatch(r"steam.*\.desktop", f)]
        if auto:
            self.add("Plasma autostart", FAIL, f"{', '.join(auto)} would start a second Steam next to steam.service",
                     "gaming-mode/install.sh")
        else:
            self.add("Plasma autostart", OK, "no second Steam")

    def check_login(self) -> None:
        self.group = "Login"
        dms = {}
        for dm in ("plasmalogin", "sddm"):
            _, out = self.sys.cmd("systemctl", "is-enabled", f"{dm}.service")
            dms[dm] = out.strip().splitlines()[0] if out.strip() else ""
        active = [d for d, s in dms.items() if s == "enabled"]
        if len(active) != 1:
            self.add("login manager", FAIL, f"expected Plasma Login or SDDM, found: {active or 'neither'}")
            return
        dm = active[0]
        self.add("login manager", OK, {"plasmalogin": "Plasma Login", "sddm": "SDDM"}[dm])
        if not self.sys.exists("/usr/lib/steamos/steam-set-session"):
            self.add("session switcher", FAIL, "/usr/lib/steamos/steam-set-session missing",
                     "sudo pacman -S gamescope-session-cachyos")
        conf_dir = "/etc/plasmalogin.conf.d" if dm == "plasmalogin" else "/etc/sddm.conf.d"
        files = [f"{conf_dir}/{f}" for f in (self.sys.listdir(conf_dir) or [])]
        if dm == "plasmalogin":
            files.insert(0, "/etc/plasmalogin.conf")
        else:
            files.insert(0, "/etc/sddm.conf")
        text = "\n".join(self.sys.read(f) or "" for f in files)
        if not self.sys.exists(f"{conf_dir}/zz-steamos-autologin.conf"):
            self.add("session file", FAIL, f"{conf_dir}/zz-steamos-autologin.conf missing",
                     "sudo sh gaming-mode/root/login-manager-setup.sh")
        elif re.search(r"^Relogin=true", text, re.M) and re.search(r"^User=\S+", text, re.M):
            self.add("autologin", OK, "user set, Relogin=true")
        else:
            self.add("autologin", FAIL, "needs User= and Relogin=true so a screen switch logs straight back in",
                     "sudo sh gaming-mode/root/login-manager-setup.sh")
        if dm == "plasmalogin":
            # Plasma Login reads only /etc/plasmalogin.conf, never conf.d
            _, out = self.sys.cmd("systemctl", "is-enabled", "plasmalogin-session-sync.path")
            if out.strip().startswith("enabled"):
                self.add("session sync", OK, "conf.d Session= is copied into plasmalogin.conf")
            else:
                self.add("session sync", FAIL,
                         "plasmalogin-session-sync.path not enabled: Plasma Login ignores conf.d, so it never switches session",
                         "sudo sh gaming-mode/root/login-manager-setup.sh")

    def check_environment(self) -> None:
        self.group = "Environment"
        d = "~/.config/environment.d"
        names = [f for f in (self.sys.listdir(d) or []) if f.endswith(".conf")]
        if not names:
            self.add("environment.d", SKIP, "no files")
            return
        for f in names:
            text = self.sys.read(f"{d}/{f}") or ""
            lines = [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.strip().startswith("#")]
            bad = [ln for ln in lines if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", ln)]
            if bad:
                self.add(f, FAIL, f"not an environment file (first odd line: {bad[0]!r}); systemd ignores it",
                         "move it where it belongs, e.g. ~/.config/xdg-desktop-portal/portals.conf")
                continue
            env = dict(ln.split("=", 1) for ln in lines)
            problems = []
            if env.get("PROTON_ENABLE_WAYLAND") == "1":
                problems.append("PROTON_ENABLE_WAYLAND=1 turns Steam Input off in Proton-CachyOS (double inputs on the Steam Controller)")
            for vendor, prefixes in VENDOR_VARS.items():
                if vendor in self.vendors:
                    continue
                wrong = sorted(k for k in env if k.startswith(prefixes))
                if wrong:
                    problems.append(f"{vendor.upper()}-only settings with no {vendor.upper()} card: {', '.join(wrong)}")
            if problems:
                self.add(f, FAIL if "WAYLAND" in problems[0] else WARN, "; ".join(problems), f"edit {d}/{f}, then log out and in")
            else:
                self.add(f, OK, f"{len(env)} variables")

    def run(self) -> list[Result]:
        self.check_gpu()
        self.check_config()
        self.check_environment()
        if self.gaming_mode_wanted():
            self.check_packages()
            self.check_files()
            self.check_units()
            self.check_steam()
            self.check_login()
        else:
            self.group = "Gaming Mode"
            self.add("Gaming Mode", SKIP, "not set up on this PC (no mode has gamescope_output)")
        return self.results


def _sink_card(sink: str) -> str | None:
    """alsa_output.<card>.<profile> -> alsa_card.<card>"""
    m = re.match(r"^alsa_output\.(.+)\.[^.]+$", sink)
    return f"alsa_card.{m.group(1)}" if m else None


MARK = {OK: " ok  ", WARN: " warn", FAIL: " FAIL", SKIP: " skip"}


def render(results: list[Result]) -> str:
    out, group = [], None
    for r in results:
        if r.group != group:
            group = r.group
            out.append(f"\n{group}")
        out.append(f" {MARK[r.status]}  {r.name}" + (f": {r.detail}" if r.detail else ""))
        if r.fix and r.status in (WARN, FAIL):
            out.append(f"          fix: {r.fix}")
    n = {s: sum(r.status == s for r in results) for s in MARK}
    out.append(f"\n{n[OK]} ok, {n[WARN]} warnings, {n[FAIL]} failed, {n[SKIP]} skipped")
    return "\n".join(out).lstrip("\n")


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="easy-switch doctor", description="Check this PC's setup. Changes nothing.")
    p.add_argument("--json", action="store_true", help="machine-readable results")
    p.add_argument("--record", action="store_true", help=argparse.SUPPRESS)  # test recording, see tests/capture.sh
    args = p.parse_args(argv)
    sys_ = Recorder() if args.record else System()
    results = Doctor(sys_).run()
    if args.record:
        print(sys_.dump())
        return 0
    if args.json:
        print(json.dumps([asdict(r) for r in results], indent=1))
    else:
        print(render(results))
    return 1 if any(r.status == FAIL for r in results) else 0
