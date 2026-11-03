# Gaming Mode (SteamOS-style gamescope session) + easy-switch

How to give a CachyOS + KDE Plasma PC a Steam-Deck-style **Gaming Mode** that
works with a Steam Controller, HDR, and easy-switch's per-screen modes. First
built on **bonestorm** (basement, RTX 4080 SUPER, LG HDMI TV + DP monitor) on
2026-11-03; written so another host (e.g. **lisa**, upstairs, RX 7900 XTX) can be
set up from this file alone.

Everything host-side lives in [`gaming-mode/`](gaming-mode/): templates
(`@HOME@` is filled in by the installer), a user installer, and a root script.

---

## Why Gaming Mode at all

The goal was: Steam Controller (2026) with correct per-game Steam Input layouts
(back grips, controller glyphs) **and** HDR on the TV.

On the KDE desktop you can't have both on NVIDIA:

| Approach | Steam Input | HDR | Notes |
|---|---|---|---|
| Proton on XWayland (`PROTON_ENABLE_WAYLAND=0`) | ✅ | ❌ | XWayland can't pass HDR to games |
| Native Wayland Proton (`PROTON_ENABLE_WAYLAND=1`) | ❌ | ✅ | Proton-CachyOS sets `PROTON_NO_STEAMINPUT=1` (via `setdefault`). Forcing `PROTON_NO_STEAMINPUT=0` keeps Steam Input *on*, but Steam can't see the Wayland window as the game, so it applies the **Desktop layout** (B = Escape, keyboard glyphs). |
| Nested gamescope on the desktop (`gamescope … -- %command%`) | ❌ | ✅ | Same focus problem: the gamescope window is a Wayland client Steam can't identify. |
| **Gaming Mode** (`gamescope-session-cachyos`) | ✅ | ✅ | gamescope owns the display; Steam always knows the focused game. **Chosen.** |

So: **keep `PROTON_ENABLE_WAYLAND=0` on the desktop**, and use Gaming Mode when
you want HDR/couch play. Switching is a logout/login (automatic, ~10 s).

---

## What you end up with

| Action | Result |
|---|---|
| Double-click **Return to Gaming Mode** (desktop icon) | Logs out, autologs into Gaming Mode on the screen easy-switch says is current |
| Steam → Power → **Switch to Desktop** | Back to Plasma |
| **Ctrl+Alt+Down / Ctrl+Alt+Up** (physical keyboard) | Switch screen. On the desktop: KDE shortcut → easy-switch. In Gaming Mode: easy-switch listener → restarts Gaming Mode on the other screen |
| **Ctrl+Alt+R** (physical keyboard, Gaming Mode) | Restart Gaming Mode on the same screen |
| Library tiles *Switch to TV / Switch to Desk Monitor / Restart Gaming Mode* | Same as the hotkeys, from the controller (add them as Non-Steam games) |
| Reboot from Gaming Mode | Back into Gaming Mode. Reboot from Plasma → Plasma |
| Gaming Mode crashes / fails to start | Relogs into **Plasma** (never a crash loop) |
| Any Steam game running | `performance` power profile + sleep inhibited, no launch option needed |

Launch options are now only for real per-game fixes (`-nolauncher`,
`VKD3D_CONFIG=…`); global settings live in `~/.config/environment.d/gaming.conf`.

---

## Architecture

```
Plasma ──icon──► easy-switch --sync ─► steamos-session-select gamescope
   ▲                                     (writes conf.d/zz-steamos-autologin.conf,
   │                                      logs out; login manager relogs)
   │                                                │
   │                                  gamescope-session.service
   │                                  + drop-in easy-switch.conf:
   │                                     EnvironmentFile=gamescope.env  (OUTPUT_CONNECTOR=<screen>,*)
   │                                     MANGOHUD=0                      (Steam uses mangoapp)
   │                                     ExecStopPost=gaming-mode-stopped
   │                                                │
   │   gamescope-session.target wants:  steam-launcher (Steam -steamdeck -gamepadui)
   │                                    easy-switch-hotkeys (evdev listener)
   │                                    gaming-mode-diag   (per-session log)
   │                                                │
   └──── gaming-mode-stopped decides next login ◄───┘
          flag $XDG_RUNTIME_DIR/easy-switch-gamescope-restart  → stay Gaming Mode (screen switch / restart)
          system shutting down                                   → stay Gaming Mode (reboot returns here)
          otherwise (crash, Switch to Desktop)                   → Plasma
```

easy-switch pieces (in the CLI itself, see README):

- `gamescope_output = "HDMI-A-1"` per mode → written to `~/.config/easy-switch/gamescope.env`.
- Inside Gaming Mode (`$XDG_RUNTIME_DIR/gamescope-environment` exists) `easy-switch <mode>`
  skips kscreen, sets audio/MangoHud, writes the env file, and restarts the session if the screen changed.
- `--restore` (Plasma autostart) re-applies a mode picked in Gaming Mode; `--sync`
  records whichever mode matches the screens that are actually on.
- `--watch-hotkeys` + per-mode `hotkey` + top-level `restart_hotkey`.
- `--restart-gaming-mode`.

---

## Setup on a new host

Do these **in order**. Steps marked 🔒 need `sudo` (the user runs them).

### 0. Prerequisites

- CachyOS, KDE Plasma, Steam (native package) already working on the desktop.
- easy-switch cloned and working on the desktop (`./install.sh`, modes in
  `~/.config/easy-switch/config.toml`, KDE shortcuts). See [README](README.md).
  lisa's starting point is [`examples/living-room.toml`](examples/living-room.toml) — verify output and sink names with `kscreen-doctor -o` and `pactl list short sinks`.
- Shared env: `~/.config/environment.d/gaming.conf` (bonestorm's copy is in
  [`gaming-mode/examples/environment.d-gaming.conf`](gaming-mode/examples/environment.d-gaming.conf)).
  **On AMD:** comment the NVIDIA block, enable the AMD block (`MESA_SHADER_CACHE_MAX_SIZE`,
  `ENABLE_LAYER_MESA_ANTI_LAG`), and for RDNA3 (7900 XTX) consider `PROTON_FSR4_RDNA3_UPGRADE=1`.
  Keep `PROTON_ENABLE_WAYLAND=0`.

### 1. 🔒 Packages

```bash
sudo pacman -S gamescope-session-cachyos python-evdev
sudo usermod -aG input "$USER"     # only if `id -nG` lacks input; log out/in after
```

`gamescope-session-cachyos` pulls `jupiter-hw-support` (Steam Deck bits). Reviewed
on bonestorm: its BIOS/controller updaters check DMI and exit on non-Valve hardware;
it adds USB automount udev rules and a GPU-reset rule. Harmless on a desktop.
Note `gamescope-session` deletes the *oldest games in `~/.local/share/Steam/steamapps`*
if `/home` has < 500 MB free (SteamOS behavior) — keep libraries on another disk or keep space free.

### 2. User side

```bash
cd ~/Projects/easy-switch/gaming-mode
./install.sh            # AMD/Intel.  NVIDIA: ./install.sh --nvidia
```

Installs (backs up any differing existing file as `*.pre-gaming-mode`):

| File | Purpose |
|---|---|
| `~/.local/bin/gaming-mode-stopped` | Decides next login when Gaming Mode ends (see architecture) |
| `~/.local/bin/steam-game-performance` + `steam-game-performance.service` | Holds `powerprofilesctl` performance + `systemd-inhibit` while any `reaper SteamLaunch AppId=` process exists. Replaces per-game `game-performance %command%` |
| `~/.local/bin/steam-clean-launch-options` | One-off: strips `game-performance`, redundant `PROTON_ENABLE_WAYLAND=0`, and `gamescope … --` wrappers from every game's launch options. Dry run by default; `--apply` with Steam **fully exited** (backs up localconfig.vdf) |
| `~/.local/bin/gaming-mode-diag` + `gaming-mode-diag.service` | Per-session snapshot (versions, gamescope cmdline, connector props, HDR metadata, kernel infoframes, screenshots) → `~/.local/state/gaming-mode-diag/`. `gaming-mode-diag mark bad "note"` |
| `~/.local/bin/gaming-mode-cycle [rounds] [secs]` | Automated in/out test loop for display bugs; rounds numbered in the diag index |
| `~/.config/systemd/user/gamescope-session.service.d/easy-switch.conf` | Screen selection, `MANGOHUD=0`, stop hook |
| `~/.config/systemd/user/easy-switch-hotkeys.service` | evdev hotkey listener, only in Gaming Mode (`PartOf=gamescope-session.target`) |
| `~/.config/systemd/user/steam.service` | Desktop Steam autostart: `-silent -steamdeck`, `PartOf=graphical-session.target`, skipped when `%t/gamescope-environment` exists |
| `~/.local/share/applications/steam.desktop` | Copy of the system launcher with `-steamdeck` |
| `~/Desktop/gaming-mode.desktop` (+ app menu copy) | "Return to Gaming Mode" |
| `~/.local/share/applications/easy-switch-{couch,desk}.desktop`, `gaming-mode-restart.desktop` | For Steam → Add a Non-Steam Game (controller-usable tiles). **Edit `Exec=` mode names to match the host's modes** (lisa uses `tv`/`desk` in the example) |
| `~/.config/autostart/easy-switch-restore.desktop` | Plasma login: `easy-switch --restore; easy-switch --sync` |
| `~/.config/MangoHud/{desk,couch}.conf` | Per-mode fps cap (only if missing; rename to match modes) |
| `~/.config/inhibit-short-session-tracker` | Disables Gaming Mode's Steam auto-reset (see pitfalls) |
| masks `cachyos-gamescope-autologin.service` | Stops every Plasma login from re-arming Gaming Mode |

### 3. 🔒 Login manager

```bash
sudo sh ~/Projects/easy-switch/gaming-mode/root/login-manager-setup.sh
```

Sets autologin `User=`, `Relogin=true`. On **Plasma Login** it edits
`/etc/plasmalogin.conf` directly and installs `plasmalogin-session-sync.path`
(copies `Session=` from `conf.d/zz-steamos-autologin.conf` into the main file —
Plasma Login ignores `conf.d`). On **SDDM** a `conf.d` file is enough.
Check with `systemctl show -p Id --value display-manager`.
This means the PC boots and logs straight in without a password (same as a Steam Deck).

### 4. easy-switch config

Add to each mode in `~/.config/easy-switch/config.toml`:

```toml
restart_hotkey = "ctrl+alt+r"      # top level, before any [modes.*]

[modes.tv]
# … existing keys …
mangohud = "couch.conf"            # optional desktop fps profile
gamescope_output = "HDMI-A-1"      # DRM connector name (same as kscreen-doctor)
hotkey = "ctrl+alt+down"           # match the KDE shortcut for this mode
```

bonestorm's full config: [`gaming-mode/examples/bonestorm-config.toml`](gaming-mode/examples/bonestorm-config.toml).
Then on the desktop run `easy-switch --sync` once (records current mode).

### 5. Steam settings (once)

- **Beta**: if the user is on Steam Beta, both clients must use `steamdeck_publicbeta`
  (installer converts `publicbeta`). In Gaming Mode: Settings → System → Steam Client
  Update Channel → **Beta**. Verify: `cat ~/.local/share/Steam/package/beta` → `steamdeck_publicbeta`,
  and switching desktop↔Gaming Mode does **not** log `Downloading update` each time.
- In Gaming Mode on each screen: Settings → Display → turn **off** "Automatically Set Resolution",
  set **Resolution** to native (Steam otherwise defaults the UI and "Native" to 1080p on 4K TVs).
- HDR: Settings → Display → Enable HDR (per screen).
- Per-game fps cap in Gaming Mode: `…` → Performance (MangoHud profiles only apply on the desktop).
- Add the three Non-Steam tiles from desktop Steam (Games → Add a Non-Steam Game).

### 6. Clean launch options (optional)

Quit Steam fully, then `steam-clean-launch-options` (review) and `steam-clean-launch-options --apply`.

### 7. Verify

| Check | How |
|---|---|
| Enters Gaming Mode on the right screen | Desktop icon; `pgrep -af '^/usr/bin/gamescope'` shows `-O <screen>,*` |
| Steam Input in a game | Back grips work, controller glyphs (not keyboard) |
| HDR | Game offers HDR; Steam overlay (`…` → Performance, level ≥2) shows `HDR ON` |
| Env reaches games | `tr '\0' '\n' </proc/<game pid>/environ \| grep -E 'PROTON_\|MANGOHUD'` (MANGOHUD=0 in Gaming Mode) |
| Screen switch | Ctrl+Alt+Up/Down in Gaming Mode → Steam restarts on the other screen |
| Restart | Ctrl+Alt+R → back in ~15 s, same screen |
| Switch to Desktop | Lands in Plasma, `easy-switch --restore/--sync` re-applies layout |
| Reboot from Gaming Mode | Comes back in Gaming Mode |
| Perf profile | `journalctl --user -u steam-game-performance` shows hold/release per game |

---

## Pitfalls hit on bonestorm (don't repeat)

1. **Plasma Login ignores `/etc/plasmalogin.conf.d/`.** Relogin there did nothing → user
   left at the greeter, then locked out by `pam_faillock` (3 bad tries → 10 min). Fix: main file
   + sync path unit (step 3). Recovery if stuck: **Restart** from the greeter (boot autologin uses
   the main file; faillock state is in `/run`, cleared on reboot).
2. **`cachyos-gamescope-autologin.service`** (preset-enabled) re-arms Gaming Mode on every Plasma
   login. Masked by the installer.
3. **Crash-loop safety vs. reboot persistence.** Don't reset the session to Plasma at Gaming Mode
   *start* (breaks reboot→Gaming Mode). Decide at *stop* (`gaming-mode-stopped`).
4. **Two Steams.** A user `steam.service` without `PartOf=graphical-session.target` survived the
   Plasma logout into Gaming Mode; desktop Steam then came back hung. Also gate it with
   `ConditionPathExists=!%t/gamescope-environment`.
5. **Steam client channel tug-of-war.** Gaming Mode runs the Deck client (`-steamdeck`), which
   only accepts `steamdeck_*` channels; plain desktop Steam rejects them and resets to `''`.
   Each side then rewrites `package/beta` → ~400 MB download on *every* switch. Fix: desktop Steam
   also runs `-steamdeck` (as SteamOS does), channel `steamdeck_publicbeta`.
6. **Steam auto-reset.** `steam-short-session-tracker` moves `~/.steam` aside after 3 Gaming Mode
   sessions < 60 s (easy to hit while testing). It wiped `registry.vdf` (OOBE again, language prompt,
   autologin user, beta). Fix: `~/.config/inhibit-short-session-tracker`. Backup lands in
   `~/dot-steam.bak.<epoch>`; restore its `registry.vdf` with Steam closed.
7. **MangoHud double overlay.** `MANGOHUD=1` from environment.d also applies in Gaming Mode;
   set `MANGOHUD=0` in the session drop-in (Steam's overlay is mangoapp).
8. **Controller can't trigger custom shortcuts in Gaming Mode.** Steam reads the controller via
   hidraw and injects Steam Input keys straight into gamescope (libei), not evdev — the listener
   sees nothing (verified: 0 events from 18 devices while pressing A/R4). The Deck UI has no
   editable Guide Button Chord layout. Desktop-layout bindings don't apply in Gaming Mode menus.
   Use a physical keyboard or the Non-Steam library tiles.
9. **Testing hotkeys with a uinput keyboard also hits KDE.** Ctrl+Alt+Up/Down from a test
   device ran the real KDE shortcuts. Stub `subprocess.Popen` and expect KDE to react, or test
   with unbound combos.
10. **Python stdout to the journal is buffered** — set `PYTHONUNBUFFERED=1` in services you want logs from.
11. **`gamescope-session.service` has `TimeoutStartSec=5`**; any `ExecStartPre` delay needs a higher timeout.

## NVIDIA-only: intermittent torn TV picture (unresolved on bonestorm)

Symptom: some Gaming Mode starts on the 4K60 HDMI TV show torn/offset/discoloured blocks for the
whole session (sometimes flickering); the DP 1440p monitor never did. ~70 % of starts at first,
~20 % after turning off Steam's "Automatically Set Resolution" (UI stays native 4K instead of
1080p→4K scaling).

Ruled out by testing/logging: HDR on/off, LG HDMI Deep Colour (already on), HDMI bandwidth/cable
(KDE drives the same 4K60 HDR fine), start-up timing (4 s pre-start delay — removed), Steam
start latency. `gaming-mode-diag` showed **identical** DRM state (mode, `Colorspace=9`,
`HDR_OUTPUT_METADATA` bytes, infoframes) in good vs bad sessions, and **gamescope's own
screenshots (incl. 8-shot bursts) were clean while the TV was torn** → corruption is after
composition (NVIDIA 615.78 scanout), not gamescope/Steam.

Still installed on bonestorm (harmless, didn't fix it): `--force-composition` wrapper and
`drm_debug_disable_explicit_sync` Lua script (`./install.sh --nvidia`). gamescope also
segfaults on exit under NVIDIA (harmless; the stop hook sends you to Plasma anyway).
Workaround: Ctrl+Alt+R / Restart tile. Candidate for an NVIDIA bug report with the diag logs.

**On AMD (lisa) none of this is expected** — install without `--nvidia`, and only reach for
`gaming-mode-diag` / `gaming-mode-cycle` if a display problem shows up.

## AMD notes for lisa (RX 7900 XTX)

- gamescope's DRM backend, HDR, and VRR are developed on AMD first (Steam Deck); expect HDR + VRR
  to just work. VRR toggle: `…` → Performance in Gaming Mode.
- Skip `--nvidia`. Don't copy NVIDIA env vars (`__GL_*`, `PROTON_NVIDIA_LIBS`, `PROTON_DLSS_UPGRADE`).
- Desktop HDR in games via native Wayland Proton is more viable on Mesa, but the Steam Input focus
  problem (table above) is the same — Gaming Mode is still the answer for controller + HDR.
- Check the TV's HDMI port/Deep Colour setting if 4K HDR misbehaves; AMD over HDMI 2.1 FRL needs a
  capable port/cable.

## Undo

```bash
sudo pacman -R gamescope-session-cachyos jupiter-hw-support
sudo systemctl disable --now plasmalogin-session-sync.path; sudo rm /usr/local/bin/plasmalogin-session-sync /etc/systemd/system/plasmalogin-session-sync.*
sudo rm -f /etc/plasmalogin.conf.d/zz-steamos-autologin.conf   # and remove Relogin/User from /etc/plasmalogin.conf if unwanted
systemctl --user disable easy-switch-hotkeys gaming-mode-diag steam-game-performance
systemctl --user unmask cachyos-gamescope-autologin.service
rm -r ~/.config/systemd/user/gamescope-session.service.d ~/.local/share/applications/steam.desktop
# restore any *.pre-gaming-mode backups
```
