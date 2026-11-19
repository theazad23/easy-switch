"""`easy-switch install`: the user half of the Gaming Mode setup (no root).

Safe to run again at any time. Files from manifest.py are symlinked into the
repo (or generated, for desktop entries); a different file already in the way
is kept once as <name>.pre-gaming-mode. NVIDIA-only files are installed where a
screen runs on NVIDIA and moved out of the way everywhere else.

The root half (login manager) stays a script the owner runs:
    sudo sh gaming-mode/root/login-manager-setup.sh
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import time
import tomllib
from pathlib import Path

from . import gpu as gpumod
from . import manifest
from .system import System

BACKUP = ".pre-gaming-mode"


class Installer:
    def __init__(self, home: str, nvidia: bool, dry_run: bool = False, runner=None, out=print) -> None:
        self.home = home
        self.nvidia = nvidia
        self.dry = dry_run
        self.run_cmd = runner or self._run
        self.out = out
        self.changed = 0

    # ------------------------------------------------------------- primitives

    def p(self, dest: str) -> Path:
        return Path(self.home + dest[1:] if dest.startswith("~") else dest)

    def say(self, verb: str, what: str) -> None:
        self.changed += 1
        self.out(f"  {'would ' if self.dry else ''}{verb} {what}")

    @staticmethod
    def _run(cmd: list[str]) -> int:
        try:
            return subprocess.run(cmd, capture_output=True, text=True).returncode
        except FileNotFoundError:
            return 127

    def backup(self, path: Path) -> None:
        """Keep the first differing file that was ever in the way."""
        b = path.with_name(path.name + BACKUP)
        if b.exists() or b.is_symlink():
            if not self.dry:
                path.unlink()
            return
        self.say("back up", f"{path} -> {b.name}")
        if not self.dry:
            path.rename(b)

    def link(self, src: Path, dest: str) -> None:
        d = self.p(dest)
        if d.is_symlink() and os.readlink(d) == str(src):
            return
        if d.is_symlink():
            if not self.dry:
                d.unlink()
        elif d.exists():
            # the old installer copied files and wrote the home path where units now say %h
            if d.read_text(errors="replace").replace(self.home, "%h") == src.read_text(errors="replace"):
                if not self.dry:
                    d.unlink()  # same file: nothing to keep
            else:
                self.backup(d)
        self.say("link", f"{dest} -> {src}")
        if not self.dry:
            d.parent.mkdir(parents=True, exist_ok=True)
            d.symlink_to(src)

    def write(self, dest: str, content: str, mode: int = 0o644, ours: bool = True) -> None:
        """`ours`: a file only this installer ever writes (generated from the repo),
        so an older version of it is replaced without a backup."""
        d = self.p(dest)
        if not d.is_symlink() and d.exists() and d.read_text(errors="replace") == content:
            return
        if d.is_symlink() or d.exists():
            if ours:
                if not self.dry:
                    d.unlink()
            else:
                self.backup(d)
        self.say("write", dest)
        if not self.dry:
            d.parent.mkdir(parents=True, exist_ok=True)
            d.write_text(content)
            d.chmod(mode)

    def set_aside(self, dest: str, stamp: str) -> None:
        d = self.p(dest)
        if not (d.exists() or d.is_symlink()):
            return
        keep = self.p(f"~/.local/state/easy-switch/removed/{stamp}") / d.name
        self.say("remove", f"{dest} (NVIDIA-only; kept in {keep.parent})")
        if not self.dry:
            keep.parent.mkdir(parents=True, exist_ok=True)
            d.rename(keep)

    # ------------------------------------------------------------------ steps

    def files(self) -> None:
        self.out("== files")
        stamp = time.strftime("%Y%m%d-%H%M%S")
        for it in manifest.items():
            if it.when == "nvidia" and not self.nvidia:
                self.set_aside(it.dest, stamp)
            elif it.how == "link":
                self.link(it.src, it.dest)
            else:
                exe = 0o755 if "/Desktop/" in it.dest else 0o644
                self.write(it.dest, manifest.rendered(it, self.home), exe)

    def mode_launchers(self) -> None:
        cfg = self.p("~/.config/easy-switch/config.toml")
        try:
            modes = tomllib.loads(cfg.read_text()).get("modes", {})
        except (OSError, tomllib.TOMLDecodeError):
            modes = {}
        if not modes:
            self.out("  ! no modes in ~/.config/easy-switch/config.toml: no 'Switch to <mode>' launchers; run again after `easy-switch add`")
        for name, m in modes.items():
            dest, text = manifest.mode_launcher(name, m.get("description", ""), self.home)
            self.write(dest, text)

    def steam(self) -> None:
        self.out("== Steam")
        # A Plasma autostart Steam would run next to steam.service: two Steams, and
        # without -steamdeck (the client channel tug-of-war).
        auto = self.p("~/.config/autostart")
        for f in sorted(auto.glob("steam*.desktop")) if auto.is_dir() else []:
            if re.search(r"^Exec=.*steam", f.read_text(errors="replace"), re.M):
                self.backup(f)
        # Desktop Steam must be the Deck client too, or it and Gaming Mode fight over
        # the client channel and re-download ~400 MB on every switch.
        stock = Path("/usr/share/applications/steam.desktop")
        if stock.is_file():
            lines = stock.read_text().splitlines()
            lines = [re.sub(r"^(Exec=/usr/bin/steam)( |$)", r"\1 -steamdeck\2", ln) for ln in lines]
            lines.insert(1, "# Local copy: adds -steamdeck so desktop Steam uses the same client/channel as Gaming Mode")
            self.write("~/.local/share/applications/steam.desktop", "\n".join(lines) + "\n", ours=False)
        flag = self.p("~/.config/inhibit-short-session-tracker")
        if not flag.exists():
            self.say("create", "~/.config/inhibit-short-session-tracker (Gaming Mode's Steam auto-reset off)")
            if not self.dry:
                flag.parent.mkdir(parents=True, exist_ok=True)
                flag.touch()
        beta = self.p("~/.local/share/Steam/package/beta")
        if beta.is_file() and beta.read_text().strip() == "publicbeta":
            self.say("set", "Steam beta channel -> steamdeck_publicbeta (shared by desktop + Gaming Mode)")
            if not self.dry:
                beta.write_text("steamdeck_publicbeta")

    def mangohud(self, repo_profiles: Path) -> None:
        """Seed FPS-cap profiles named by the modes, only where missing."""
        if not repo_profiles.is_dir():
            return
        self.out("== MangoHud profiles (only if missing)")
        for f in sorted(repo_profiles.glob("*.conf")):
            d = self.p(f"~/.config/MangoHud/{f.name}")
            if not d.exists():
                self.write(f"~/.config/MangoHud/{f.name}", f.read_text())

    def services(self) -> None:
        self.out("== services")
        cmds = [
            ["systemctl", "--user", "daemon-reload"],
            # CachyOS default: every Plasma login re-arms autologin into Gaming Mode. We
            # want "last mode wins" (gaming-mode-stopped + the session drop-in).
            ["systemctl", "--user", "mask", "cachyos-gamescope-autologin.service"],
            ["systemctl", "--user", "enable", *manifest.USER_UNITS],
            ["systemctl", "--user", "restart", "steam-game-performance.service"],
        ]
        for c in cmds:
            if self.dry:
                self.out(f"  would run {' '.join(c)}")
            else:
                rc = self.run_cmd(c)
                self.out(f"  {' '.join(c[2:])}" + ("" if rc == 0 else f"  (exit {rc})"))

    def run(self, mangohud_dir: Path | None = None) -> int:
        self.out(f"== GPU: NVIDIA extras {'yes' if self.nvidia else 'no'}")
        self.files()
        self.mode_launchers()
        self.steam()
        if mangohud_dir:
            self.mangohud(mangohud_dir)
        self.services()
        if self.changed == 0:
            self.out("\nnothing to change")
        self.out(
            "\nnext: sudo sh gaming-mode/root/login-manager-setup.sh (once per PC), then `easy-switch doctor`"
        )
        return 0


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(
        prog="easy-switch install",
        description="Install or refresh the Gaming Mode files for this user (no root). Safe to re-run.",
    )
    p.add_argument("--dry-run", action="store_true", help="show what would change, change nothing")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--nvidia", action="store_true", help="force the NVIDIA-only gamescope workarounds")
    g.add_argument("--no-nvidia", action="store_true", help="force without them")
    args = p.parse_args(argv)
    detected = "nvidia" in gpumod.vendors(gpumod.detect(System()))
    nvidia = True if args.nvidia else False if args.no_nvidia else detected
    if nvidia != detected:
        print(f"  ! NVIDIA extras forced {'ON' if nvidia else 'OFF'}; this PC's screens run on {'NVIDIA' if detected else 'another driver'}")
    host = (os.uname().nodename or "").split(".")[0]
    return Installer(str(Path.home()), nvidia, args.dry_run).run(manifest.GM / "mangohud" / host)
