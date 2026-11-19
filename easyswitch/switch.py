#!/usr/bin/env python3
"""KDE display + audio mode switcher driven by a TOML config."""

from __future__ import annotations

import argparse
import datetime
import os
import re
import socket
import subprocess
import sys
import time
import tomllib
from pathlib import Path
from typing import Any

KSCREEN_SETTLE_SECONDS = 1.0  # gap between the enable batch and the disable batch

DEFAULT_CONFIG = Path(
    os.environ.get("EASY_SWITCH_CONFIG")
    or Path.home() / ".config" / "easy-switch" / "config.toml"
)

ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
OUTPUT_HEADER_RE = re.compile(r"^Output:\s+\d+\s+(\S+)")
CONNECTED_RE = re.compile(r"\bconnected\b")  # \b prevents matching inside "disconnected"
STARRED_MODE_RE = re.compile(r"\d+:(\d+x\d+)@(\d+(?:\.\d+)?)\*")
GEOMETRY_RE = re.compile(r"Geometry:\s+(-?\d+,-?\d+)\s+(\d+x\d+)")
ROTATION_KEYWORD = {1: "normal", 2: "left", 4: "inverted", 8: "right"}
NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")
MANGOHUD_DIR = (
    Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "MangoHud"
)
STATE_DIR = (
    Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state")
    / "easy-switch"
)
LAST_MODE_FILE = STATE_DIR / "last-mode"
# Set when a mode is applied inside Gaming Mode, where KDE's layout can't be
# touched; the next Plasma login re-applies the mode via `--restore`.
PENDING_PLASMA_FILE = STATE_DIR / "pending-plasma"
# Read by the gamescope-session.service drop-in (EnvironmentFile=).
GAMESCOPE_ENV_FILE = (
    Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    / "easy-switch"
    / "gamescope.env"
)


def die(msg: str, code: int = 1) -> None:
    print(f"easy-switch: {msg}", file=sys.stderr)
    sys.exit(code)


def load_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        die(
            f"no config at {path}. Run `easy-switch add <name>` to create one, "
            "or copy from examples/."
        )
    with path.open("rb") as f:
        return tomllib.load(f)


def run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
    """subprocess.run with friendly errors when the binary is missing."""
    try:
        return subprocess.run(cmd, **kwargs)
    except FileNotFoundError:
        die(f"required command not found: {cmd[0]}")


def drm_attr(name: str, attr: str) -> str | None:
    """Read /sys/class/drm/cardX-<NAME>/<attr>. Returns None if unavailable."""
    base = Path("/sys/class/drm")
    if not base.is_dir():
        return None
    for d in base.iterdir():
        if not d.is_dir():
            continue
        # Connector dirs look like "card1-HDMI-A-1" — strip "cardN-".
        parts = d.name.split("-", 1)
        if len(parts) == 2 and parts[1] == name:
            try:
                return (d / attr).read_text().strip()
            except OSError:
                return None
    return None


def parse_outputs() -> dict[str, dict[str, Any]]:
    """Detect every output kscreen-doctor knows about and its current state."""
    result = run(
        ["kscreen-doctor", "-o"], capture_output=True, text=True, check=True
    )
    text = ANSI_RE.sub("", result.stdout)

    outputs: dict[str, dict[str, Any]] = {}
    current: dict[str, Any] | None = None

    for raw in text.splitlines():
        m = OUTPUT_HEADER_RE.match(raw)
        if m:
            current = {
                "connected": False,
                "enabled": False,
                "primary": False,
                "mode": None,
                "position": None,
                "rotation": "normal",
            }
            outputs[m.group(1)] = current
            continue
        if current is None:
            continue
        line = raw.strip()
        if line == "enabled":
            current["enabled"] = True
        elif line == "disabled":
            current["enabled"] = False
        elif CONNECTED_RE.search(line):
            current["connected"] = True
        elif line.startswith("priority "):
            parts = line.split()
            if len(parts) >= 2 and parts[1].isdigit() and int(parts[1]) == 1:
                current["primary"] = True
        elif line.startswith("Modes:"):
            sm = STARRED_MODE_RE.search(line)
            if sm:
                current["mode"] = f"{sm.group(1)}@{round(float(sm.group(2)))}"
        elif line.startswith("Geometry:"):
            gm = GEOMETRY_RE.search(line)
            if gm:
                current["position"] = gm.group(1)
        elif line.startswith("Rotation:"):
            parts = line.split()
            if len(parts) >= 2 and parts[1].isdigit():
                current["rotation"] = ROTATION_KEYWORD.get(int(parts[1]), "normal")

    return outputs


def connected_outputs() -> set[str]:
    return {n for n, info in parse_outputs().items() if info["connected"]}


def detect_sinks() -> list[dict[str, str]]:
    """All currently visible pactl sinks, with friendly descriptions."""
    result = run(
        ["pactl", "list", "sinks"], capture_output=True, text=True, check=True
    )
    sinks: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    for raw in result.stdout.splitlines():
        if raw.startswith("Sink #"):
            if current and current.get("name"):
                sinks.append(current)
            current = {"name": "", "description": ""}
        elif current is not None:
            stripped = raw.strip()
            if stripped.startswith("Name:"):
                current["name"] = stripped.split(":", 1)[1].strip()
            elif stripped.startswith("Description:"):
                current["description"] = stripped.split(":", 1)[1].strip()
    if current and current.get("name"):
        sinks.append(current)
    return sinks


def notify(
    summary: str,
    body: str = "",
    urgency: str = "normal",
    icon: str | None = None,
) -> None:
    cmd = ["notify-send", "--app-name=Easy Switch", f"--urgency={urgency}"]
    if icon:
        cmd.append(f"--icon={icon}")
    cmd += [summary, body]
    try:
        # Bounded: with no notification daemon (Gaming Mode on CachyOS:
        # steam-notif-daemon's binary is missing) notify-send blocks on D-Bus
        # activation for ~40 s. That once held up a hotkey screen switch.
        subprocess.run(cmd, check=False, timeout=2)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass  # notify-send absent or no daemon — non-fatal


def humanize_missing(required: list[str]) -> str:
    """Render a `requires_any` failure for a human: any-of semantics."""
    if len(required) == 1:
        return f"{required[0]} isn't connected"
    if len(required) == 2:
        return f"neither {required[0]} nor {required[1]} is connected"
    return f"none of {', '.join(required)} are connected"


ALSA_SINK_RE = re.compile(r"^alsa_output\.(?P<card>.+)\.(?P<profile>[^.]+)$")
SINK_APPEAR_SECONDS = 3.0


def sink_card_profile(sink: str) -> tuple[str, str] | None:
    """`alsa_output.<card>.<suffix>` -> (`alsa_card.<card>`, card profile that
    creates it): `pro-output-N` lives in `pro-audio`, anything else (e.g.
    `hdmi-stereo-extra1`, `analog-stereo`) in `output:<suffix>`."""
    m = ALSA_SINK_RE.match(sink)
    if not m:
        return None
    suffix = m["profile"]
    profile = "pro-audio" if suffix.startswith("pro-output-") else f"output:{suffix}"
    return f"alsa_card.{m['card']}", profile


def sink_exists(sink: str) -> bool:
    out = run(["pactl", "list", "short", "sinks"], capture_output=True, text=True, check=True)
    return any(line.split("\t")[1:2] == [sink] for line in out.stdout.splitlines())


def set_audio(sink: str) -> None:
    # An ALSA sink only exists while its card is in the matching profile. Steam
    # (Gaming Mode) and WirePlumber both switch card profiles — e.g. on lisa the
    # Navi HDMI card left `pro-audio`, so `pro-output-7` vanished — so select
    # the profile first if the sink isn't there, then wait for it to appear.
    if not sink_exists(sink) and (cp := sink_card_profile(sink)):
        run(["pactl", "set-card-profile", *cp], check=True)
        deadline = time.monotonic() + SINK_APPEAR_SECONDS
        while not sink_exists(sink) and time.monotonic() < deadline:
            time.sleep(0.1)
    run(["pactl", "set-default-sink", sink], check=True)


# ---------------------------------------------------------------------------
# Apply
# ---------------------------------------------------------------------------


def set_mangohud(profile: str) -> None:
    """Point MangoHud.conf at this mode's profile. MangoHud re-reads it on every
    game launch and the symlink survives reboots, so the last mode sticks."""
    target = MANGOHUD_DIR / Path(profile).expanduser()
    if not target.is_file():
        raise FileNotFoundError(f"MangoHud profile {target} doesn't exist")
    link = MANGOHUD_DIR / "MangoHud.conf"
    if link.exists() and not link.is_symlink():
        raise FileExistsError(f"{link} is a regular file; move it aside first")
    tmp = link.with_name(".MangoHud.conf.tmp")
    tmp.unlink(missing_ok=True)
    tmp.symlink_to(target)
    os.replace(tmp, link)  # atomic swap so a game launching mid-switch never sees no config


def in_gaming_mode() -> bool:
    """True inside the SteamOS-style gamescope session. The session writes this
    file once gamescope is up and removes it on exit (same check upstream uses)."""
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    return bool(runtime) and (Path(runtime) / "gamescope-environment").exists()


def read_gamescope_output() -> str | None:
    try:
        for line in GAMESCOPE_ENV_FILE.read_text().splitlines():
            if line.startswith("OUTPUT_CONNECTOR="):
                return line.split("=", 1)[1]
    except OSError:
        pass
    return None


def remember_mode(name: str, mode_cfg: dict[str, Any]) -> None:
    """Record the last applied mode and which screen Gaming Mode should use."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    LAST_MODE_FILE.write_text(name + "\n")
    output = mode_cfg.get("gamescope_output")
    if output:
        GAMESCOPE_ENV_FILE.parent.mkdir(parents=True, exist_ok=True)
        # Trailing "*" lets gamescope fall back to any screen if this one is gone.
        GAMESCOPE_ENV_FILE.write_text(f"OUTPUT_CONNECTOR={output},*\n")


def restart_gaming_mode(reason: str) -> int:
    """Restart the gamescope session on the same screen (e.g. to clear a torn
    picture). The flag tells the host's session-stop hook to relog into Gaming
    Mode instead of falling back to Plasma."""
    if not in_gaming_mode():
        print("easy-switch: not in Gaming Mode; nothing to restart", file=sys.stderr)
        return 2
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    if runtime:
        (Path(runtime) / "easy-switch-gamescope-restart").touch()
    # --no-block queues the stop in systemd, so it completes even though
    # this process is a child of the session and dies with it. Queue it
    # before anything that could block (notify).
    run(["systemctl", "--user", "--no-block", "stop", "gamescope-session.target"], check=False)
    notify("Restarting Gaming Mode", reason)
    return 0


def apply_mode_gaming(name: str, mode_cfg: dict[str, Any], dry_run: bool) -> int:
    """Apply a mode from inside Gaming Mode. gamescope owns the displays, so
    instead of kscreen we point it at the mode's screen and restart the session
    (the login manager relogs straight back into Gaming Mode)."""
    pretty = mode_cfg.get("description") or name
    failed_title = f"Couldn't switch to {pretty}"
    output = mode_cfg.get("gamescope_output")
    if not output:
        msg = f"mode '{name}' has no gamescope_output, so Gaming Mode can't use it"
        print(f"easy-switch: {msg}", file=sys.stderr)
        if not dry_run:
            notify(failed_title, msg, urgency="critical", icon="dialog-error")
        return 2
    if drm_attr(output, "status") != "connected":
        msg = f"{output} isn't connected. No changes were made."
        print(f"easy-switch: {msg}", file=sys.stderr)
        if not dry_run:
            notify(failed_title, msg, urgency="critical", icon="dialog-error")
        return 2

    restart = read_gamescope_output() != f"{output},*"
    if dry_run:
        print(f"would write: {GAMESCOPE_ENV_FILE}: OUTPUT_CONNECTOR={output},*")
        if mode_cfg.get("audio"):
            print(f"would run: pactl set-default-sink {mode_cfg['audio']}")
        if restart:
            print("would run: systemctl --user --no-block stop gamescope-session.target")
        return 0

    # Non-fatal: the screen switch is what matters here.
    try:
        if mode_cfg.get("mangohud"):
            set_mangohud(mode_cfg["mangohud"])
        if mode_cfg.get("audio"):
            set_audio(mode_cfg["audio"])
    except (OSError, subprocess.CalledProcessError) as e:
        print(f"easy-switch: {e}", file=sys.stderr)
    remember_mode(name, mode_cfg)
    PENDING_PLASMA_FILE.touch()

    if restart:
        restart_gaming_mode(f"Steam will restart on {pretty}.")
    else:
        notify(f"Switched to {pretty}", mode_cfg.get("description", ""))
    return 0


def expected_primary(mode_cfg: dict[str, Any]) -> str | None:
    """Which output the mode says should end up primary."""
    for name, ocfg in mode_cfg.get("outputs", {}).items():
        if ocfg.get("primary") and ocfg.get("enable", True):
            return name
    return None


def verify_output_alive(
    name: str,
    expected_mode: str | None,
    ocfg: dict[str, Any] | None = None,
) -> tuple[bool, str]:
    """Best-effort check that an output we just enabled actually came up.

    There's no fully-reliable way to detect a TV in standby vs. a TV that's
    on but not yet receiving signal — every signal we can read (kscreen
    `connected`, DRM `status`/`dpms`, ALSA ELD `monitor_present`) is either
    cached or correlated with "signal flowing," not "panel actually on."
    So this verifier only catches the cases where kscreen itself didn't
    flip state: enabled=false, wrong mode, or DPMS still Off. It is not
    expected to catch the "TV is in standby" case, and that limitation is
    documented in the README. `ocfg` is reserved for future per-output
    checks if a usable signal ever turns up.
    """
    del ocfg  # reserved
    info = parse_outputs().get(name) or {}
    if not info:
        return False, f"{name} vanished from kscreen-doctor"
    if not info.get("enabled"):
        return False, f"{name} did not switch to enabled — the display may be off"
    if expected_mode and info.get("mode") != expected_mode:
        return False, (
            f"{name} did not apply mode {expected_mode} — the display may be off"
        )

    dpms = drm_attr(name, "dpms")
    if dpms is not None and dpms != "On":
        return False, (
            f"{name} reports power state '{dpms}' — the display is not awake"
        )
    return True, ""


def build_kscreen_commands(
    mode_cfg: dict[str, Any], connected: set[str]
) -> list[list[str]]:
    """Build the kscreen-doctor invocations needed to apply this mode.

    Returns up to two commands, in order: enables (with their primary/mode/
    position/rotation flags), then disables. The caller runs them with a
    short sleep between so KDE can settle the primary-output switch.

    Combining enable+disable in one kscreen-doctor call fails with
    'Failure: No such entity' when the primary display changes mid-command —
    confirmed on the basement couch transition. Splitting matches what the
    legacy bash scripts have always done.
    """
    outputs = mode_cfg.get("outputs", {})
    enable_args: list[str] = []
    disable_args: list[str] = []

    for name, ocfg in outputs.items():
        enable = ocfg.get("enable", True)
        if not enable:
            if name in connected:
                disable_args.append(f"output.{name}.disable")
            continue
        if name not in connected:
            continue
        enable_args.append(f"output.{name}.enable")
        if ocfg.get("primary"):
            enable_args.append(f"output.{name}.primary")
        if "mode" in ocfg:
            enable_args.append(f"output.{name}.mode.{ocfg['mode']}")
        if "position" in ocfg:
            enable_args.append(f"output.{name}.position.{ocfg['position']}")
        if "rotation" in ocfg:
            enable_args.append(f"output.{name}.rotation.{ocfg['rotation']}")

    # `strict`: disable any connected output the mode didn't mention.
    # Covers the "wizard run with HDMI unplugged, HDMI plugged in later" case —
    # without strict, the unlisted output would silently stay enabled.
    if mode_cfg.get("strict"):
        listed = set(outputs.keys())
        for name in sorted(connected - listed):
            disable_args.append(f"output.{name}.disable")

    commands: list[list[str]] = []
    if enable_args:
        commands.append(["kscreen-doctor"] + enable_args)
    if disable_args:
        commands.append(["kscreen-doctor"] + disable_args)
    return commands


def apply_mode(name: str, mode_cfg: dict[str, Any], dry_run: bool) -> int:
    pretty = mode_cfg.get("description") or name
    audio = mode_cfg.get("audio")
    audio_only_fallback = mode_cfg.get("audio_only_fallback", False)
    requires_any = mode_cfg.get("requires_any", [])

    failed_title = f"Couldn't switch to {pretty}"
    partial_title = f"Switched to {pretty} (partly)"

    # 1. Probe state first (read-only). If this fails we haven't touched anything.
    connected = connected_outputs()

    # 2. Validate requirements *before* any mutation. If the required display
    #    isn't there, we make no changes — not to displays, not to audio —
    #    unless `audio_only_fallback = true` is explicitly opted in.
    if requires_any and not any(o in connected for o in requires_any):
        missing_human = humanize_missing(requires_any)
        if audio and audio_only_fallback:
            if dry_run:
                print(f"easy-switch: {missing_human}")
                print(f"would run: pactl set-default-sink {audio}")
                return 0
            print(f"easy-switch: {missing_human} — switching audio only (audio_only_fallback)")
            try:
                set_audio(audio)
            except subprocess.CalledProcessError:
                notify(
                    failed_title,
                    f"{missing_human}, and switching audio also failed.",
                    urgency="critical",
                    icon="dialog-error",
                )
                return 2
            notify(
                f"Switched to {pretty} (audio only)",
                f"{missing_human.capitalize()}. Audio set to {audio}.",
                urgency="normal",
                icon="dialog-warning",
            )
            return 0
        print(f"easy-switch: {missing_human} — no changes made")
        if not dry_run:
            notify(
                failed_title,
                f"{missing_human.capitalize()}. No changes were made.",
                urgency="critical",
                icon="dialog-error",
            )
        return 2

    # 3. Now we know we're applying. Reset kscreen state so connection detection
    #    is fresh, then re-probe.
    if not dry_run:
        run(["kscreen-doctor", "configure"], check=False)
        connected = connected_outputs()
        if requires_any and not any(o in connected for o in requires_any):
            missing_human = humanize_missing(requires_any)
            print(f"easy-switch: {missing_human} (after reset) — no changes made")
            notify(
                failed_title,
                f"{missing_human.capitalize()} after refreshing display state. No changes were made.",
                urgency="critical",
                icon="dialog-error",
            )
            return 2

    # 4. Apply displays. Enables first, then disables, with a settle gap —
    #    combining both in a single kscreen-doctor command can fail with
    #    "No such entity" when the primary output changes mid-command.
    #    Between the two batches we verify the new primary actually woke up;
    #    if not, we skip the disable batch so the user isn't left with a
    #    blank screen because the TV was off / cable bad / display asleep.
    commands = build_kscreen_commands(mode_cfg, connected)
    primary_target = expected_primary(mode_cfg)
    for i, cmd in enumerate(commands):
        if dry_run:
            print("would run:", " ".join(cmd))
            continue
        try:
            run(cmd, check=True)
        except subprocess.CalledProcessError as e:
            print(
                f"easy-switch: kscreen-doctor apply failed (exit {e.returncode}) "
                "— audio left unchanged",
                file=sys.stderr,
            )
            notify(
                failed_title,
                f"kscreen-doctor exited {e.returncode} while applying the layout. Audio was left unchanged.",
                urgency="critical",
                icon="dialog-error",
            )
            return 2
        # Between enable batch (i=0) and disable batch (i=1): verify the
        # primary actually came up before we kill the other outputs.
        if i < len(commands) - 1:
            if primary_target and primary_target in connected:
                target_cfg = mode_cfg["outputs"][primary_target]
                expected_mode = target_cfg.get("mode")
                # Poll: a responsive panel settles within ~1s, a slow CEC
                # wake can take 2-3s. Give it up to 3s total before giving up.
                deadline = time.monotonic() + 3.0
                ok = False
                reason = ""
                while time.monotonic() < deadline:
                    time.sleep(0.25)
                    ok, reason = verify_output_alive(
                        primary_target, expected_mode, target_cfg
                    )
                    if ok:
                        break
                if not ok:
                    msg = (
                        f"{reason}. Other displays were left alone — "
                        "run another mode (e.g. `easy-switch desk`) to restore."
                    )
                    print(f"easy-switch: {msg}", file=sys.stderr)
                    notify(
                        failed_title,
                        msg,
                        urgency="critical",
                        icon="dialog-error",
                    )
                    return 2
            else:
                time.sleep(KSCREEN_SETTLE_SECONDS)

    # 5. MangoHud profile and audio only after a successful display apply.
    mangohud = mode_cfg.get("mangohud")
    if mangohud:
        if dry_run:
            print(f"would link: {MANGOHUD_DIR / 'MangoHud.conf'} -> {mangohud}")
        else:
            try:
                set_mangohud(mangohud)
            except OSError as e:
                notify(
                    partial_title,
                    f"Displays updated, but couldn't switch MangoHud profile: {e}",
                    urgency="normal",
                    icon="dialog-warning",
                )
                return 2

    if audio:
        if dry_run:
            print(f"would run: pactl set-default-sink {audio}")
        else:
            try:
                set_audio(audio)
            except subprocess.CalledProcessError:
                notify(
                    partial_title,
                    f"Displays updated, but couldn't set audio to {audio}.",
                    urgency="normal",
                    icon="dialog-warning",
                )
                return 2

    if not dry_run:
        remember_mode(name, mode_cfg)
        notify(
            f"Switched to {pretty}",
            mode_cfg.get("description", ""),
            urgency="normal",
            icon="preferences-desktop-display",
        )
    return 0


def detect_active_mode(config: dict[str, Any]) -> str | None:
    """Which configured mode matches the screens that are actually on right now:
    its primary output is enabled and every output it disables is off. Reads DRM
    sysfs, so it works without a display connection."""
    for name, mode_cfg in config.get("modes", {}).items():
        primary = expected_primary(mode_cfg)
        if not primary or drm_attr(primary, "enabled") != "enabled":
            continue
        if any(
            drm_attr(o, "enabled") == "enabled"
            for o, ocfg in mode_cfg.get("outputs", {}).items()
            if ocfg.get("enable") is False
        ):
            continue
        return name
    return None


def cmd_sync(config: dict[str, Any], dry_run: bool) -> int:
    """Make the recorded mode (Gaming Mode screen, MangoHud profile) match the
    screen that's on, e.g. after KDE restored a layout at login. Audio and the
    display layout are left alone."""
    name = detect_active_mode(config)
    if name is None:
        print("easy-switch: current screens don't match any mode — nothing recorded")
        return 0
    mode_cfg = config["modes"][name]
    if dry_run:
        print(f"would record mode: {name}")
        return 0
    if mode_cfg.get("mangohud"):
        try:
            set_mangohud(mode_cfg["mangohud"])
        except OSError as e:
            print(f"easy-switch: {e}", file=sys.stderr)
    remember_mode(name, mode_cfg)
    print(f"easy-switch: recorded mode {name}")
    return 0


MODIFIER_KEYS = {
    "ctrl": ("KEY_LEFTCTRL", "KEY_RIGHTCTRL"),
    "alt": ("KEY_LEFTALT", "KEY_RIGHTALT"),
    "shift": ("KEY_LEFTSHIFT", "KEY_RIGHTSHIFT"),
    "meta": ("KEY_LEFTMETA", "KEY_RIGHTMETA"),
}


def parse_hotkey(spec: str) -> tuple[frozenset[str], str]:
    """"ctrl+alt+down" -> ({"ctrl", "alt"}, "KEY_DOWN")."""
    *mods, key = [part.strip().lower() for part in spec.split("+")]
    unknown = [m for m in mods if m not in MODIFIER_KEYS]
    if unknown or not key:
        die(f"bad hotkey '{spec}': modifiers are {', '.join(MODIFIER_KEYS)}")
    return frozenset(mods), f"KEY_{key.upper()}"


RESTART = "\0restart"  # sentinel binding target; can't collide with a mode name


def cmd_watch_hotkeys(config: dict[str, Any]) -> int:
    """Gaming Mode has no KDE global shortcuts, so watch keyboards directly
    (evdev, read-only, no grab: keys still reach the game) for each mode's
    `hotkey` and switch to it. Steam Input's virtual keyboard is a keyboard
    too, so a Steam-button chord bound to the same keys works here as well."""
    import selectors

    import evdev  # python-evdev; only needed for this subcommand
    from evdev import ecodes

    bindings: dict[tuple[frozenset[str], int], str] = {}
    for name, mode_cfg in config.get("modes", {}).items():
        if mode_cfg.get("hotkey"):
            mods, key = parse_hotkey(mode_cfg["hotkey"])
            if key not in ecodes.ecodes:
                die(f"unknown key in hotkey '{mode_cfg['hotkey']}'")
            bindings[(mods, ecodes.ecodes[key])] = name
    restart_spec = config.get("restart_hotkey")
    if restart_spec:
        mods, key = parse_hotkey(restart_spec)
        if key not in ecodes.ecodes:
            die(f"unknown key in restart_hotkey '{restart_spec}'")
        bindings[(mods, ecodes.ecodes[key])] = RESTART
    if not bindings:
        die("no modes have a `hotkey`; nothing to watch")
    mod_codes = {
        ecodes.ecodes[k]: mod for mod, keys in MODIFIER_KEYS.items() for k in keys
    }
    trigger_codes = {code for _, code in bindings}

    sel = selectors.DefaultSelector()
    devices: dict[str, Any] = {}
    held: dict[str, set[str]] = {}

    def rescan() -> None:
        # Re-run every couple of seconds: Steam's virtual keyboard and
        # hotplugged keyboards show up after we start.
        for path in evdev.list_devices():
            if path in devices:
                continue
            try:
                dev = evdev.InputDevice(path)
            except OSError:
                continue
            keys = set(dev.capabilities().get(ecodes.EV_KEY, []))
            if not keys & trigger_codes:
                dev.close()
                continue
            devices[path] = dev
            held[path] = set()
            sel.register(dev, selectors.EVENT_READ, path)

    def drop(path: str) -> None:
        dev = devices.pop(path)
        held.pop(path, None)
        sel.unregister(dev)
        try:
            dev.close()
        except OSError:
            pass

    labels = [
        restart_spec + " -> restart" if n == RESTART else config["modes"][n]["hotkey"] + " -> " + n
        for n in bindings.values()
    ]
    print(f"easy-switch: watching hotkeys: {', '.join(labels)}")
    rescan()
    while True:
        for sk, _ in sel.select(timeout=2.0):
            path = sk.data
            try:
                events = list(devices[path].read())
            except OSError:  # unplugged
                drop(path)
                continue
            for ev in events:
                if ev.type != ecodes.EV_KEY or ev.value == 2:  # ignore autorepeat
                    continue
                if ev.code in mod_codes:
                    (held[path].add if ev.value else held[path].discard)(mod_codes[ev.code])
                    continue
                mode = bindings.get((frozenset(held[path]), ev.code)) if ev.value == 1 else None
                if mode == RESTART:
                    print("easy-switch: hotkey -> restart Gaming Mode")
                    subprocess.Popen([sys.executable, os.path.realpath(__file__), "--restart-gaming-mode"])
                elif mode:
                    print(f"easy-switch: hotkey -> {mode}")
                    subprocess.Popen([sys.executable, os.path.realpath(__file__), mode])
        rescan()


def cmd_restore(config: dict[str, Any], dry_run: bool) -> int:
    """Plasma login hook: re-apply the mode last chosen in Gaming Mode, if any."""
    if not PENDING_PLASMA_FILE.exists():
        return 0
    try:
        name = LAST_MODE_FILE.read_text().strip()
    except OSError:
        name = ""
    modes = config.get("modes", {})
    if name not in modes:
        PENDING_PLASMA_FILE.unlink(missing_ok=True)
        return 0
    rc = apply_mode(name, modes[name], dry_run=dry_run)
    if rc == 0 and not dry_run:
        PENDING_PLASMA_FILE.unlink(missing_ok=True)
    return rc


def list_modes(config: dict[str, Any]) -> int:
    modes = config.get("modes", {})
    if not modes:
        die("no modes defined in config")
    width = max(len(n) for n in modes)
    for name, m in modes.items():
        print(f"{name.ljust(width)}  {m.get('description', '')}")
    return 0


# ---------------------------------------------------------------------------
# Wizard (`add`)
# ---------------------------------------------------------------------------


def confirm(prompt: str, default: bool) -> bool:
    suffix = "[Y/n]" if default else "[y/N]"
    try:
        ans = input(f"{prompt} {suffix} ").strip().lower()
    except EOFError:
        return default
    if not ans:
        return default
    return ans in {"y", "yes"}


def prompt_text(prompt: str, default: str | None = None) -> str | None:
    suffix = f" [{default}]" if default else ""
    try:
        ans = input(f"{prompt}{suffix}: ").strip()
    except EOFError:
        return default
    return ans or default


def snapshot_outputs(detected: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Turn detected state into a mode.outputs dict."""
    recorded: dict[str, dict[str, Any]] = {}
    for name, info in detected.items():
        if info["enabled"] and info["connected"]:
            entry: dict[str, Any] = {"enable": True}
            if info["primary"]:
                entry["primary"] = True
            if info["mode"]:
                entry["mode"] = info["mode"]
            if info["position"] and info["position"] != "0,0":
                entry["position"] = info["position"]
            if info["rotation"] != "normal":
                entry["rotation"] = info["rotation"]
            recorded[name] = entry
        elif info["connected"]:
            recorded[name] = {"enable": False}
        # Disconnected outputs are omitted — we have no info to record.
    return recorded


def describe_output(name: str, info: dict[str, Any]) -> str:
    if not info["connected"]:
        return f"  {name}: not connected — skipped"
    if not info["enabled"]:
        return f"  {name}: connected, disabled — will disable when present"
    parts = []
    if info["primary"]:
        parts.append("primary")
    if info["mode"]:
        parts.append(info["mode"])
    parts.append(f"at {info['position'] or '0,0'}")
    if info["rotation"] != "normal":
        parts.append(f"rotation {info['rotation']}")
    return f"  {name}: " + ", ".join(parts)


def cmd_remove(name: str, config_path: Path, force: bool) -> int:
    if not config_path.exists():
        die(f"no config at {config_path}")
    text = config_path.read_text()
    existing = tomllib.loads(text)
    modes = existing.get("modes", {})
    if name not in modes:
        available = ", ".join(modes) or "(none)"
        die(f"no such mode '{name}'. Configured: {available}")

    if not force:
        desc = modes[name].get("description", "")
        prompt = f"Remove mode '{name}'"
        if desc:
            prompt += f" — \"{desc}\""
        prompt += "?"
        if not confirm(prompt, default=False):
            print("Aborted.")
            return 1

    new_text = delete_mode_block(text, name)
    config_path.write_text(new_text)
    print(f"Removed mode '{name}' from {config_path}.")
    return 0


def cmd_add(name: str, config_path: Path, force: bool) -> int:
    if not NAME_RE.match(name):
        die(f"mode name '{name}' must contain only letters, digits, '-', '_'")

    existing_text: str | None = None
    existing_modes: dict[str, Any] = {}
    if config_path.exists():
        existing_text = config_path.read_text()
        existing_modes = tomllib.loads(existing_text).get("modes", {})
        if name in existing_modes and not force:
            if not confirm(f"Mode '{name}' already exists. Overwrite?", default=False):
                print("Aborted.")
                return 1
            force = True

    print("Detecting displays...")
    detected = parse_outputs()
    if not detected:
        die("kscreen-doctor reported no outputs")
    for n, info in detected.items():
        print(describe_output(n, info))
    print()

    recorded = snapshot_outputs(detected)
    if not any(e.get("enable") for e in recorded.values()):
        die("no enabled outputs to snapshot. Configure displays first, then re-run.")

    sinks = detect_sinks()
    audio: str | None = None
    if sinks:
        print("Audio sinks:")
        for i, s in enumerate(sinks, 1):
            line = f"  {i}. {s['name']}"
            if s["description"]:
                line += f"  ({s['description']})"
            print(line)
        print("  0. skip (don't change audio in this mode)")
        choice = prompt_text("Pick sink", "1")
        try:
            idx = int(choice) if choice else 1
        except ValueError:
            die(f"invalid sink choice: {choice}")
        if idx != 0:
            if not 1 <= idx <= len(sinks):
                die(f"sink choice {idx} out of range")
            audio = sinks[idx - 1]["name"]
    else:
        print("No audio sinks detected (pactl returned nothing) — skipping audio.")

    description = prompt_text("Description (optional)", None)

    primaries = [n for n, e in recorded.items() if e.get("primary")]
    enabled_names = [n for n, e in recorded.items() if e.get("enable")]
    default_required = primaries or enabled_names[:1]
    print()
    print("Required displays — at least one must be connected for the mode to apply.")
    print(f"  All currently enabled: {', '.join(enabled_names)}")
    print(f"  Default: {', '.join(default_required)}")
    req_raw = prompt_text("Required (comma-separated, blank for default)", "")
    if req_raw:
        requires_any = [s.strip() for s in req_raw.split(",") if s.strip()]
    else:
        requires_any = default_required

    audio_only_fallback = False
    if audio:
        audio_only_fallback = confirm(
            "Switch audio anyway if required display is missing?", default=False
        )

    mode: dict[str, Any] = {}
    if description:
        mode["description"] = description
    if requires_any:
        mode["requires_any"] = requires_any
    # `strict` defaults to true for snapshots so an output that wasn't connected
    # at snapshot time still gets disabled when it shows up later.
    mode["strict"] = True
    if audio:
        mode["audio"] = audio
    if audio_only_fallback:
        mode["audio_only_fallback"] = True
    mode["outputs"] = recorded

    action = write_mode_to_config(config_path, name, mode, existing_text)
    print(f"\nSaved mode '{name}' to {config_path} ({action}).")
    print(f"Run with: easy-switch {name}")
    return 0


# ---------------------------------------------------------------------------
# TOML emitter + merge
# ---------------------------------------------------------------------------


def emit_value(v: Any) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, str):
        return '"' + v.replace("\\", "\\\\").replace('"', '\\"') + '"'
    if isinstance(v, list):
        return "[" + ", ".join(emit_value(x) for x in v) + "]"
    raise TypeError(f"cannot emit value of type {type(v).__name__}")


def emit_mode_block(name: str, mode: dict[str, Any]) -> str:
    lines = [f"[modes.{name}]"]
    for key in ("description", "requires_any", "strict", "audio", "audio_only_fallback", "mangohud", "gamescope_output", "hotkey"):
        if key in mode:
            lines.append(f"{key} = {emit_value(mode[key])}")
    for oname, ocfg in mode.get("outputs", {}).items():
        lines.append("")
        lines.append(f"[modes.{name}.outputs.{oname}]")
        for key in ("enable", "primary", "mode", "position", "rotation"):
            if key in ocfg:
                lines.append(f"{key} = {emit_value(ocfg[key])}")
    return "\n".join(lines)


def delete_mode_block(text: str, name: str) -> str:
    """Strip out the [modes.<name>] block and its subtables from `text`.
    Returns the text unchanged if the mode isn't there.
    """
    lines = text.splitlines(keepends=True)
    header = f"[modes.{name}]"
    sub_prefix = f"[modes.{name}."
    start: int | None = None
    end: int | None = None
    for i, line in enumerate(lines):
        s = line.strip()
        if start is None:
            if s == header:
                start = i
        else:
            if s.startswith("[") and s != header and not s.startswith(sub_prefix):
                end = i
                break
    if start is None:
        return text
    if end is None:
        end = len(lines)
    # Trim trailing blank lines that belonged to the removed block.
    while end > start + 1 and lines[end - 1].strip() == "":
        end -= 1
    # Trim one leading blank line so we don't accumulate empty space.
    if start > 0 and lines[start - 1].strip() == "":
        start -= 1
    return "".join(lines[:start]) + "".join(lines[end:])


def replace_mode_block(text: str, name: str, new_block: str) -> str:
    """Splice new_block in place of the existing [modes.<name>] block."""
    lines = text.splitlines(keepends=True)
    header = f"[modes.{name}]"
    sub_prefix = f"[modes.{name}."
    start: int | None = None
    end: int | None = None
    for i, line in enumerate(lines):
        s = line.strip()
        if start is None:
            if s == header:
                start = i
        else:
            if s.startswith("[") and s != header and not s.startswith(sub_prefix):
                end = i
                break
    if start is None:
        return text.rstrip() + "\n\n" + new_block + "\n"
    if end is None:
        end = len(lines)
    # Trim trailing blank lines that belonged to the old block so we don't accumulate.
    while end > start + 1 and lines[end - 1].strip() == "":
        end -= 1
    suffix = "\n" if end < len(lines) else ""
    return "".join(lines[:start]) + new_block + "\n" + suffix + "".join(lines[end:])


def write_mode_to_config(
    path: Path, name: str, mode: dict[str, Any], existing_text: str | None
) -> str:
    block = emit_mode_block(name, mode)
    if existing_text is None:
        path.parent.mkdir(parents=True, exist_ok=True)
        host = socket.gethostname()
        today = datetime.date.today().isoformat()
        header = f"# easy-switch config for host {host} — generated {today}\n\n"
        path.write_text(header + block + "\n")
        return "created"

    existing = tomllib.loads(existing_text)
    if name in existing.get("modes", {}):
        path.write_text(replace_mode_block(existing_text, name, block))
        return "replaced"

    sep = "\n" if existing_text.endswith("\n") else "\n\n"
    if not existing_text.endswith("\n\n"):
        sep = "\n\n" if existing_text.endswith("\n") else "\n\n"
    path.write_text(existing_text.rstrip() + "\n\n" + block + "\n")
    return "added"


# ---------------------------------------------------------------------------
# Entry
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="easy-switch",
        description="Switch KDE display + audio modes from a TOML config.",
    )
    p.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help=f"config path (default: {DEFAULT_CONFIG})",
    )
    p.add_argument(
        "--list", action="store_true", help="list configured modes and exit"
    )
    p.add_argument(
        "--restart-gaming-mode",
        action="store_true",
        help="restart Gaming Mode on the same screen (inside Gaming Mode only)",
    )
    p.add_argument(
        "--watch-hotkeys",
        action="store_true",
        help="run forever, switching modes on each mode's `hotkey` (for Gaming Mode)",
    )
    p.add_argument(
        "--sync",
        action="store_true",
        help="record whichever mode matches the screens that are on now",
    )
    p.add_argument(
        "--restore",
        action="store_true",
        help="re-apply the mode last chosen in Gaming Mode (run at Plasma login)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="print commands that would run, change nothing",
    )
    p.add_argument(
        "mode",
        nargs="?",
        help="mode name to apply; or 'add <name>' to record one, "
        "'remove <name>' to delete one",
    )
    p.add_argument(
        "rest", nargs=argparse.REMAINDER, help=argparse.SUPPRESS
    )
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.restart_gaming_mode:
        return restart_gaming_mode("Steam will be back in a few seconds.")

    if args.mode == "add":
        if not args.rest:
            die("usage: easy-switch add <name> [--force]")
        name = args.rest[0]
        force = "--force" in args.rest[1:]
        try:
            return cmd_add(name, args.config, force=force)
        except KeyboardInterrupt:
            print("\nAborted.", file=sys.stderr)
            return 130

    if args.mode in ("remove", "rm"):
        if not args.rest:
            die(f"usage: easy-switch {args.mode} <name> [--force]")
        name = args.rest[0]
        force = "--force" in args.rest[1:]
        try:
            return cmd_remove(name, args.config, force=force)
        except KeyboardInterrupt:
            print("\nAborted.", file=sys.stderr)
            return 130

    config = load_config(args.config)

    if args.list:
        return list_modes(config)

    if args.restore:
        return cmd_restore(config, dry_run=args.dry_run)

    if args.sync:
        return cmd_sync(config, dry_run=args.dry_run)

    if args.watch_hotkeys:
        return cmd_watch_hotkeys(config)

    if not args.mode:
        parser.print_help()
        return 1

    modes = config.get("modes", {})
    if args.mode not in modes:
        available = ", ".join(modes) or "(none)"
        die(f"unknown mode '{args.mode}'. Available: {available}")

    if in_gaming_mode():
        return apply_mode_gaming(args.mode, modes[args.mode], dry_run=args.dry_run)
    return apply_mode(args.mode, modes[args.mode], dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
