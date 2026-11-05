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
| **Per-mode hotkeys** (physical keyboard; bonestorm Ctrl+Alt+Up/Down, lisa Ctrl+Alt+Left/Right) | Switch screen. On the desktop: KDE shortcut → easy-switch. In Gaming Mode: easy-switch listener → restarts Gaming Mode on the other screen |
| **Ctrl+Alt+R** (physical keyboard, Gaming Mode) | Restart Gaming Mode on the same screen |
| Library tiles *Switch to &lt;mode&gt;* (one per mode) / *Restart Gaming Mode* | Same as the hotkeys, from the controller (add them as Non-Steam games) |
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
  Mode names are per host (bonestorm `desk`/`couch`, lisa `desk`/`tv`); the installer
  generates launchers from whatever modes `config.toml` has, so **set the config up first**.
- Shared env: `~/.config/environment.d/gaming.conf`. Per-host copies:
  [`bonestorm-environment.d-gaming.conf`](gaming-mode/examples/bonestorm-environment.d-gaming.conf) (NVIDIA),
  [`lisa-environment.d-gaming.conf`](gaming-mode/examples/lisa-environment.d-gaming.conf) (AMD).
  **On AMD:** comment the NVIDIA block, enable the AMD block (`MESA_SHADER_CACHE_MAX_SIZE`,
  `ENABLE_LAYER_MESA_ANTI_LAG`), and for RDNA3 (7900 XTX) `PROTON_FSR4_RDNA3_UPGRADE=1`
  (lisa: on — FSR4 costs a few fps vs FSR3 at the same internal res but looks much better;
  opt a game out with `PROTON_FSR4_RDNA3_UPGRADE=0 %command%`). Keep `PROTON_ENABLE_WAYLAND=0`.

### 1. 🔒 Packages

```bash
sudo pacman -S gamescope-session-cachyos python-evdev
sudo usermod -aG input "$USER"     # only if `id -nG` lacks input; log out/in after
```

**NVIDIA:** after step 2, build the GBM-patched gamescope (`gaming-mode/nvidia/gamescope-gbm-git/update.sh`), see the NVIDIA section.

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
| `~/.local/bin/gaming-mode-cycle [rounds] [secs] [delays…]` | Automated in/out test loop for display bugs; rounds numbered in the diag index. See [display test toolkit](#display-test-toolkit) |
| `~/.local/bin/gaming-mode-{test-form,extra-args,delay,hdmi-link}` + `~/.local/share/gaming-mode/test-form/` | Display test toolkit (phone form, per-start flags, start delay, HDMI link monitor) |
| `--nvidia` only: wrapper, `nvidia.conf` + `start-delay.conf` drop-ins, `50-nvidia-tv-fix.lua` | NVIDIA fixes; also build `gamescope-gbm-git` ([NVIDIA section](#nvidia-corrupted--flickering-4k-tv-picture-in-gaming-mode-solved-gbm-scan-out)) |
| `~/.config/systemd/user/gamescope-session.service.d/easy-switch.conf` | Screen selection, `MANGOHUD=0`, stop hook |
| `~/.config/systemd/user/easy-switch-hotkeys.service` | evdev hotkey listener, only in Gaming Mode (`PartOf=gamescope-session.target`) |
| `~/.config/systemd/user/steam.service` | Desktop Steam autostart: `-silent -steamdeck`, `PartOf=graphical-session.target`, skipped when `%t/gamescope-environment` exists |
| `~/.local/share/applications/steam.desktop` | Copy of the system launcher with `-steamdeck` |
| `~/Desktop/gaming-mode.desktop` (+ app menu copy) | "Return to Gaming Mode" |
| `~/.local/share/applications/easy-switch-<mode>.desktop` ("Switch to <mode>"), `gaming-mode-restart.desktop` | For Steam → Add a Non-Steam Game (controller-usable tiles). One per mode in `config.toml`, generated from `applications/easy-switch-mode.desktop.in` (re-run the installer after adding/renaming modes) |
| `~/.config/autostart/easy-switch-restore.desktop` | Plasma login: `easy-switch --restore; easy-switch --sync` |
| `~/.config/autostart/steam*.desktop` → `*.pre-gaming-mode` | Disables a Plasma-autostarted Steam (would run next to `steam.service`, without `-steamdeck`) |
| `~/.config/MangoHud/<mode>.conf` | Per-mode fps cap from `mangohud/<hostname>/` (only if missing). New host: copy a host dir, name files after the modes, set `fps_limit` for the screens |
| `~/.config/inhibit-short-session-tracker` | Disables Gaming Mode's Steam auto-reset (see pitfalls) |
| masks `cachyos-gamescope-autologin.service` | Stops every Plasma login from re-arming Gaming Mode |

### 3. 🔒 Login manager

```bash
sudo sh ~/Projects/easy-switch/gaming-mode/root/login-manager-setup.sh
```

Sets autologin `User=`, `Relogin=true`. On **Plasma Login** it edits
`/etc/plasmalogin.conf` directly and installs `plasmalogin-session-sync.path`
(copies `Session=` from `conf.d/zz-steamos-autologin.conf` into the main file —
Plasma Login ignores `conf.d`). On **SDDM** (lisa) it writes `/etc/sddm.conf.d/50-autologin.conf`
and comments out any `[Autologin]` `User`/`Session`/`Relogin` in `/etc/sddm.conf` (backup
`/etc/sddm.conf.pre-gaming-mode`): SDDM reads `/etc/sddm.conf` **after** `conf.d`, so a leftover
`Session=plasma` there overrides Steam's `zz-steamos-autologin.conf` and Gaming Mode never starts.
Check with `systemctl show -p Id --value display-manager`.
This means the PC boots and logs straight in without a password (same as a Steam Deck).

### 4. easy-switch config

Add to each mode in `~/.config/easy-switch/config.toml`:

```toml
restart_hotkey = "ctrl+alt+r"      # top level, before any [modes.*]

[modes.tv]
# … existing keys …
mangohud = "tv.conf"               # optional desktop fps profile (~/.config/MangoHud/<mode>.conf)
gamescope_output = "HDMI-A-1"      # DRM connector name (same as kscreen-doctor)
hotkey = "ctrl+alt+down"           # match the KDE shortcut for this mode
```

Full configs: [`bonestorm-config.toml`](gaming-mode/examples/bonestorm-config.toml),
[`lisa-config.toml`](gaming-mode/examples/lisa-config.toml). `hotkey` must match the host's KDE
shortcut for that mode — lisa already had Ctrl+Alt+Left (desk) / Ctrl+Alt+Right (tv), so it uses those.
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

Quit Steam fully (check `pgrep -x steam` is empty), then `steam-clean-launch-options` (review) and
`steam-clean-launch-options --apply`. It handles every Steam account in `userdata/`, and strips
`game-performance`, `PROTON_ENABLE_WAYLAND=0`, `gamescope … --`, `mangohud` (double overlay in
Gaming Mode), `DRI_PRIME=…` on single-GPU hosts, and fixes the `%commands` typo. lisa: 26 games
cleared, only `--skip-launcher`/`--no-launcher` kept.

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
12. **gamescope Lua may be LuaJIT** (the GBM build is): no `warn()`; a Lua error aborts gamescope and
    you land on the desktop. Use `(warn or print)(…)`.
13. **pacman `--noconfirm` answers conflict prompts with No** → installing a package that replaces
    `gamescope-git` fails. Install it interactively.

## Pitfalls hit on lisa (SDDM, AMD)

14. **`/etc/sddm.conf` beats `conf.d`.** lisa had `[Autologin] User=… Session=plasma` there from the
    CachyOS installer. SDDM reads it last, so every relogin would go to Plasma. `login-manager-setup.sh`
    now comments those keys out.
15. **Plasma autostart Steam.** `~/.config/autostart/steam.desktop` (`steam-runtime -silent`, no
    `-steamdeck`) = second Steam next to `steam.service` + channel tug-of-war. Installer moves it aside.
16. **`%commands` typo in launch options** (7 games). Steam only substitutes `%command%`; otherwise the
    whole string is appended to the game's argv, so `game-performance` silently never ran.
17. **Agent sessions across the switch.** A Claude Code session in a Plasma terminal dies with the
    logout; one run through `paseo-daemon.service` (systemd user service, the user manager outlives
    the quick relogin) keeps going in Gaming Mode — that's how lisa was set up, so the agent can
    check `gamescope-session` / diag logs live from the phone/browser.
18. **Check Steam is closed with `pgrep -x steam`**, not by eye — it was quietly started mid-setup
    and the installer rewrote `package/beta` under it (survived, but don't rely on that).
19. **Steam changes the HDMI card profile.** The first Gaming Mode session switched the Navi card from
    `pro-audio` to `output:hdmi-stereo-extra1`; after the next boot (TV off → that profile unavailable)
    WirePlumber fell back to `hdmi-stereo` (the Dell). `pro-output-7` no longer existed, `easy-switch tv`
    failed at `pactl` ("No such entity") and audio stayed on the desk speakers. Fix: use the standard
    profile sinks Steam uses (`…hdmi-stereo-extra1`), and `set_audio()` now runs `pactl set-card-profile`
    (derived from the sink name) when the sink is missing.
20. **An agent started at boot (paseo-daemon) has no Wayland env** — `kscreen-doctor` aborts (SIGABRT).
    Take `WAYLAND_DISPLAY`/`DISPLAY` from `systemctl --user show-environment`. KDE shortcuts are unaffected.
21. **No notification daemon in Gaming Mode → hotkeys looked dead.** CachyOS's `steam-notif-daemon.service`
    points at a missing `/usr/bin/steam_notif_daemon`, so `notify-send` blocked ~40 s on D-Bus activation,
    and `restart_gaming_mode()` notified *before* queueing the session stop — Ctrl+Alt+Left/Right recorded
    the new screen but never restarted. Fix: stop first, then notify; `notify()` has a 2 s timeout.

## NVIDIA: corrupted / flickering 4K TV picture in Gaming Mode (solved: GBM scan-out)

**Symptom (bonestorm, RTX 4080 SUPER → LG TV, HDMI, 4K60, driver 615.78):** a random share of
Gaming Mode starts (20–80 % depending on the day) show a broken picture for the whole session:
square tiles that flicker, filled left→right then down from a varying point (top part fine), and
on stock gamescope sometimes torn/offset/discoloured blocks. The desktop (KWin) never shows it.
Turning the TV off/on mid-session can break a clean session. gamescope's own screenshots are
always clean, and the HDMI link is perfect (see `gaming-mode-hdmi-link` below).

**Cause** (upstream ValveSoftware/gamescope
[#2309](https://github.com/ValveSoftware/gamescope/issues/2309), same hardware;
[#1593](https://github.com/ValveSoftware/gamescope/issues/1593),
[#2333](https://github.com/ValveSoftware/gamescope/issues/2333)): NVIDIA's display engine can't
scan out non-contiguous memory. gamescope allocates its scan-out images with Vulkan, which has no
way to ask for display-capable memory, so at 4K they're sometimes non-contiguous and every start
is a lottery. KWin allocates with GBM, which is why the desktop is fine. NVIDIA (cubanismo, #1593)
calls GBM "the most correct fix" and plans a gamescope-specific driver quirk; upstream gamescope
won't switch to GBM. AMD/Intel aren't affected in practice (lisa: skip all of this).

### The fix (what `./install.sh --nvidia` + one build set up)

1. **gamescope with the GBM scan-out patch**, packaged as `gamescope-gbm-git`:
   [`gaming-mode/nvidia/gamescope-gbm-git/`](gaming-mode/nvidia/gamescope-gbm-git/README.md)
   (upstream master + `0001-nvidia-gbm-scanout.patch`, from farnoy/gamescope `nvidia-gbm-wayland`,
   rebased). Replaces `gamescope`/`gamescope-git`. Build and install once:
   ```bash
   cd ~/Projects/easy-switch/gaming-mode/nvidia/gamescope-gbm-git && ./update.sh
   ```
   pacman asks to remove `gamescope-git` → **y**. `install.sh --nvidia` warns while it's missing.
2. **`~/.config/gamescope/scripts/50-nvidia-tv-fix.lua`** turns `drm_gbm_scanout` on (only if the
   binary has it, so stock gamescope ignores it) and keeps `drm_debug_disable_explicit_sync = true`
   (explicit sync ON tested much worse). Scripts must be LuaJIT-safe: `(warn or print)(…)`.
3. **The wrapper** (`~/.local/share/gaming-mode/bin/gamescope`) adds `--force-composition`.

Verify a start: `journalctl --user -u gamescope-session -b | grep -E 'gamescope version|Created GBM'`
shows a `+`-suffixed version and `Created GBM device`, and **no** "nvidia-drm detected: scanout of
Vulkan-allocated buffers is known to corrupt" line. Quirks: ~10 s to exit (systemd kills it, harmless);
`GBM allocation failed for 32x32` lines (cursor-size buffers, harmless so far).

**Updating** is manual (`pacman -Syu` won't touch it): `./update.sh --check`, then `./update.sh`.
If the patch stops applying: `./refresh-patch.sh` (rebases branch `gbm-on-master` in
`~/src/gamescope-gbm`; the package README covers conflicts).

**Drop it** when NVIDIA's driver quirk ships or upstream adopts GBM (watch #2309):
`sudo pacman -S gamescope-git`, then run a test (below) to confirm stock is clean.

### Display test toolkit

All installed by `./install.sh`; the wrapper flags need `--nvidia`. Every session is logged by
`gaming-mode-diag` to `~/.local/state/gaming-mode-diag/` (index + per-session log).

| Command | What |
|---|---|
| `gaming-mode-cycle ROUNDS SECS [delays…]` | From the desktop: enter/leave Gaming Mode ROUNDS times, SECS each (20 is enough to judge). Optional delays rotate per round |
| `GAMING_MODE_CYCLE_ARGS='none\|--flag…' gaming-mode-cycle …` | Rotate test setups per round (`\|`-separated, `none` = normal). Restores everything at the end |
| `gaming-mode-test-form start` | Phone form on `http://<host>:8766/?modes=A,B&rounds=12&title=…`: mark rounds good/bad, live "NOW ON TV" banner, Submit → `gaming-mode-test-form results`. Needs the port open: `sudo ufw allow from 192.168.10.0/24 to any port 8766 proto tcp` |
| `gaming-mode-diag mark bad "note"` | Mark the newest session by hand |
| `gaming-mode-extra-args [flags…\|none]` | Extra flags for the next start. Real gamescope flags pass through; wrapper-only: `--x-bin PATH` (other gamescope binary), `--x-convar NAME=VALUE` (set a convar), `--x-explicit-sync` (skip `50-nvidia-tv-fix.lua`) |
| `gaming-mode-delay [secs]` | Wait before gamescope starts (default 0; tested: no effect) |
| `gaming-mode-hdmi-link [watch]` | Read the TV's HDMI 2.0 SCDC registers over DDC (read-only): clock/channel lock, scrambling, character errors. diag logs it every 2 s (`*-link.log`, `LINK` line in the index). The LG TV doesn't clear its error counters, so only counts that **grow** during a session are bad; a fixed start count is link bring-up. Example: a **PC** reboot with the TV left on gave `12,12,8` for the whole session (BIOS → console → nvidia-drm → gamescope each re-set the HDMI mode; a few garbled characters per switch are normal), while desktop↔Gaming Mode switches stay at 0 |

Example, A/B of a gamescope build (what proved the fix):
```bash
gaming-mode-test-form start        # open http://<host>:8766/?modes=stock,GBM&rounds=12&title=GBM%20test
GAMING_MODE_CYCLE_ARGS="none|--x-bin $HOME/src/gamescope-gbm/build/src/gamescope --x-convar drm_gbm_scanout=true" \
    gaming-mode-cycle 12 20 0
```
Don't start a cycle while a session is still stopping, and if you stop one mid-way, remove
`$XDG_RUNTIME_DIR/easy-switch-gamescope-restart` or Gaming Mode relaunches once more.

### How to test (the method that found the cause)

Intermittent display bugs can't be judged from one start, and the bad rate drifts between days.
What worked:

1. **Automate the starts, keep a human only for the eyes.** `gaming-mode-cycle` does the
   restarts; you only look at the TV and tap good/bad on the phone form. 20 s per round is enough.
2. **A/B in the same run, alternating rounds**, never "today vs yesterday". Rotate the setups
   with `GAMING_MODE_CYCLE_ARGS` so both see the same TV/temperature/drift. 12 rounds (6 + 6) is
   the minimum; with 3 setups use 15.
3. **Change one thing per test** and keep everything else fixed (delay, monitors plugged/unplugged,
   gamescope build).
4. **Verify the setup actually applied** before trusting a round: check the journal for the
   gamescope version, the Lua `warn`/print lines, the per-round `args=` in the diag index.
5. **Describe what you see, not just bad/good** (where on screen, shape, pattern). "Squares filling
   left→right, top part fine" is what pointed at scan-out, after "flicker" didn't.
6. **Record every round** (`MARK` lines in the index) and keep the numbers in the test log below,
   including tests that didn't help: they rule things out.
7. **Search upstream once the symptom is precise.** With hardware + exact symptom in hand, the
   matching gamescope issue (#2309) and NVIDIA's explanation were one search away.
8. **Confirm a fix three times:** A/B vs stock, then the fix alone as the default, then the
   final installed package.

Rough significance check for an alternating A/B: 0/6 vs 4/6 bad is ~3 % likely by chance;
0/12 alone when the baseline is ~65 % bad is ~0.0003 %.

### Test log (2026-11-03/04, bonestorm)

Bad = rounds the user saw corruption on, by eye. Same TV, cable, 4K60, HDR on.

| Test | Result | Conclusion |
|---|---|---|
| Steam "Automatically Set Resolution" off | ~70 % → ~20 % bad (11-03) | Helps a bit, keep it off |
| HDR on/off, LG Deep Colour, startup timing | no change | — |
| gamescope screenshots while TV bad | always clean | Corruption is after composition |
| Start delay 0 / 4 / 8 / 15 s | 3/3, 1/3, 1/3, 2/3 bad | Not timing; default back to 0 |
| TV EDID | HDMI 2.0 only (600 MHz, no FRL); 4K60 = 594 MHz + scrambling | Fiber (AOC) cable was a suspect |
| SCDC link monitor, 12 rounds | 10/12 bad by eye, **249/249 samples locked, 0 errors** | Cable/HDMI link ruled out |
| `--disable-color-management` | 3/6 vs normal 5/6 | Not colour management |
| Desk monitor unplugged | 8/12 | Second display not the cause |
| stable gamescope 3.17.0 → `gamescope-git` (c3b7f78 Layer_t init) | 8/12, but flicker only (blocks gone) | Blocks partly a gamescope bug, flicker remains |
| Explicit sync ON (Lua off) | 6/6 bad, heavy blocks | Keep the Lua |
| Explicit sync + CPU wait before commit (± no in-fence) | 5/5, 4/5 | Not a fence/timing race |
| **GBM scan-out vs stock, alternating** | **GBM 0/6, stock 4/6** | **Fix** (p ≈ 0.03) |
| GBM as default | 0/12 | Confirmed |
| Installed `gamescope-gbm-git` package | 0/6 | **0/24 GBM starts** vs ~65 % bad on stock that day |
| PC reboot (TV left on) straight into Gaming Mode | clean picture; SCDC start count `12,12,8`, never growing | Reboot persistence OK; counts are boot-time mode switches, not a link problem |

Kernel note: the bad rate rose after linux-cachyos 7.3.0 → 7.3.1 (11-03), probably memory-layout
luck rather than the kernel itself; the user keeps the bleeding-edge kernel. Log mining of 60 marked
sessions found no log line that predicts a bad start, so automatic detection would need a camera
on the TV (frame-to-frame change on the static Steam UI).

## AMD notes for lisa (RX 7900 XTX)

Set up 2026-11-03. Values found:

| | lisa |
|---|---|
| Display manager | SDDM |
| Desk | `DP-1` Dell S2716DG 2560x1440@144, no VRR on AMD (G-SYNC module), no HDR → MangoHud `desk.conf` 144 fps `early` |
| TV | `HDMI-A-1` Hisense 3840x2160@60, HDR → `tv.conf` 60 fps `early` |
| Audio | desk `…Creative_Pebble_Pro_MF1710-01.analog-stereo`, TV `alsa_output.pci-0000_08_00.1.hdmi-stereo-extra1` (HDMI 2 = `eld#0.1` HISENSE, TV speakers only → stereo; `hdmi-stereo` = Dell). Was `pro-output-7` — see pitfall 19 |
| Hotkeys | Ctrl+Alt+Left desk, Ctrl+Alt+Right tv, Ctrl+Alt+R restart |
| First run | 2026-11-03: Gaming Mode on HDMI-A-1 first try, HDR on (Steam → Display), no torn/flickering picture (the NVIDIA issue does not occur), Steam only verified files (no channel re-download). Deck UI shows its first-run setup once — normal, not a reset |
| Open (2026-11-04) | Retest Ctrl+Alt+Left/Right in Gaming Mode after the notify fix (pitfall 21); remaining step 7 checks: Ctrl+Alt+R, Switch to Desktop, reboot from Gaming Mode, Non-Steam tiles, Dell display settings in Gaming Mode |

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
sudo pacman -S gamescope-git          # NVIDIA: replaces gamescope-gbm-git
rm -r ~/.config/gamescope/scripts/50-nvidia-tv-fix.lua ~/.local/share/gaming-mode
# restore any *.pre-gaming-mode backups
```
