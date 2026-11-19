# Fresh install: CachyOS + KDE Plasma (Wayland)

What to do on a new PC before and around `easy-switch install`, and why. Commands assume CachyOS
(Arch), KDE Plasma on Wayland; fish or bash.

`easy-switch doctor` checks most of this afterwards: extra drives (*System*), the Steam prompt
(*System*), the gaming packages (*System*), `environment.d` format and GPU-specific variables
(*Environment*), Steam autostart and the performance service (*Services*, *Steam*). The rest
(SSH keys, KDE Wallet) is manual and listed here.

## Second NVMe as a games/storage drive

```bash
# Partition
sudo gdisk /dev/nvme1n1
# Inside gdisk: d (delete existing partitions) → n → accept all defaults → w → y

# Format
sudo mkfs.ext4 -L fast-storage /dev/nvme1n1p1

# Create mount point
sudo mkdir -p /mnt/fast-storage

# Get UUID
sudo blkid /dev/nvme1n1p1

# Add to /etc/fstab (replace UUID with output from above)
# UUID=xxxx-xxxx  /mnt/fast-storage  ext4  defaults,nofail  0  2

# Mount and set permissions
sudo mount -a
sudo chown $USER:$USER /mnt/fast-storage
```

Then in Steam: Settings → Storage → + → select `/mnt/fast-storage`

---

## Fix Steam "Remote Control Requested" prompt on KDE Wayland

Steam requests remote desktop / input device access via xdg-desktop-portal on every launch.
Fix by pre-authorizing it in the KDE permission store:

```bash
gdbus call --session \
  --dest org.freedesktop.impl.portal.PermissionStore \
  --object-path /org/freedesktop/impl/portal/PermissionStore \
  --method org.freedesktop.impl.portal.PermissionStore.Set \
  "kde-authorized" true "remote-desktop" '{"": ["yes"]}' '<@a{sv} {}>'
```

Restart Steam after running this. No reboot needed.

> This writes to `~/.local/share/flatpak/db/kde-authorized` and persists across reboots.

---

## Fix Dolphin prompting for password when clicking unmounted drives

This goes away once the drive is in `/etc/fstab` (see above). The prompt appears because
udisks2 requires root to mount drives not listed in fstab.

---

## Steam silent autostart at login

First turn off Steam's own autostart: Steam → Settings → Interface → uncheck "Run Steam when my
computer starts".

`easy-switch install` then sets up `steam.service` (a systemd user unit): Steam starts silently
with the desktop, stops with it so it never lingers into Gaming Mode, and runs as the Deck client
(`-steamdeck`) so the desktop and Gaming Mode share one client channel. It also disables a Plasma
autostart entry for Steam if one exists (two Steams otherwise).

> `easy-switch doctor` → *Services* and *Steam* check all of this.

---

## Global gaming environment variables

Set Steam/Proton env vars once for every game, in a single file. Steam (and the
silent autostart service above) inherit these from the graphical session, and
Proton passes them through to the game.

```bash
mkdir -p ~/.config/environment.d
nano ~/.config/environment.d/gaming.conf
```

Pick the block that matches your GPU. `easy-switch doctor` flags variables that belong to the
other vendor's driver.

> **Important format rule:** `environment.d` only supports full-line `#`
> comments. Inline comments on the same line as `KEY=value` become part of the
> value (e.g. `MANGOHUD=1   # foo` makes MANGOHUD literally equal to
> `"1   # foo"`). Always put comments on their own line, and never indent
> variable lines — leading whitespace makes systemd silently skip the line.

```ini
# === Vendor-agnostic always-on ===
# FPS/CPU/GPU overlay for all Vulkan games
MANGOHUD=1

# === NVIDIA (current machine) ===
# Shader cache: 12GB + don't auto-evict
__GL_SHADER_DISK_CACHE_SIZE=12000000000
__GL_SHADER_DISK_CACHE_SKIP_CLEANUP=1

# === AMD (for the future AMD build -- comment NVIDIA block, uncomment this) ===
# MESA_SHADER_CACHE_MAX_SIZE=12G
# AMD Anti-Lag, reduced input latency
# ENABLE_LAYER_MESA_ANTI_LAG=1

# === Situational toggles -- uncomment per game/situation, not always-on ===
# NVIDIA: auto-upgrade DLSS DLL (breaks a few games)
# PROTON_DLSS_UPGRADE=1
# NVIDIA: on-screen DLSS status
# PROTON_DLSS_INDICATOR=1
# NVIDIA: PhysX/CUDA (NOT needed for DLSS/RT)
# PROTON_NVIDIA_LIBS=1
# NVIDIA: fixes RTX 4000+ perf issues
# PROTON_NVIDIA_LIBS_NO_32BIT=1
# AMD: auto-upgrade FSR
# PROTON_FSR4_UPGRADE=1
# AMD: RDNA3-optimized FSR4
# PROTON_FSR4_RDNA3_UPGRADE=1
# Intel/general: auto-upgrade XeSS
# PROTON_XESS_UPGRADE=1
# native Wayland (BREAKS Steam overlay)
# PROTON_ENABLE_WAYLAND=1
# needs Gamescope --hdr-enabled OR Wayland flag above
# PROTON_ENABLE_HDR=1
# use FSync, for games that misbehave under NTSync
# PROTON_NO_NTSYNC=1
# fix borderless fullscreen / click-through
# PROTON_NO_WM_DECORATION=1
# per-game shader cache isolation
# PROTON_LOCAL_SHADER_CACHE=1
# controller detection workaround
# PROTON_PREFER_SDL=1
# disable Steam Input (fixes Wayland gamepad issues)
# PROTON_NO_STEAMINPUT=1
```

Log out and back in (or reboot) for `environment.d` to pick the file up. Verify
Steam sees it:

```bash
systemctl --user show-environment | grep -E '__GL_|MESA_|PROTON_'
```

Verify the **NVIDIA shader cache** is actually being populated (modern driver
uses `~/.cache/nvidia/GLCache/`, not the older `~/.nv/GLCache/`):

```bash
du -sh ~/.cache/nvidia/GLCache/                                # size — grows toward the 12GB cap
find ~/.cache/nvidia/GLCache/ -type f -printf '%TY-%Tm-%Td %TH:%TM %p\n' | sort | tail -3
```

Most recent timestamps near "now" while Steam is running confirms shaders are
being written. AMD-equivalent path is `~/.cache/mesa_shader_cache/`.

Also disable **Steam's own** pre-cache (wiki-recommended when using
Proton-CachyOS, since it already ships codecs): Steam → Settings → Downloads →
uncheck **"Allow background processing of Vulkan shaders"** and **"Enable
Shader Pre-caching"**. Stored in `~/.steam/steam/config/config.vdf` as
`ShaderCacheManager.DisableShaderCache "1"`.

> **DXVK / VKD3D per-game caches** appear automatically under each game's
> `~/.steam/steam/steamapps/compatdata/<appid>/pfx/` after first launch — no env
> var needed, this is default DXVK behavior. Empty cache = no DXVK game has
> been run yet, not a misconfiguration.

> **Precedence:** Steam per-game launch options of the form `VAR=value %command%`
> override anything set here, for that one game. So this file sets the defaults
> and the Steam Properties → Launch Options field is still your per-game escape
> hatch.

> The `cachyos-gaming-meta` package pulls in MangoHud, Gamescope, etc. Install it
> via CachyOS Hello → Apps/Tweaks → Install Gaming packages (or
> `sudo pacman -S cachyos-gaming-meta cachyos-gaming-applications`).

> **MangoHud config:** edit `~/.config/MangoHud/MangoHud.conf` directly, or run
> `goverlay` for a GUI. `MANGOHUD=1` only enables the Vulkan implicit layer —
> covers anything via DXVK/VKD3D-Proton (i.e. almost every Steam game). For
> OpenGL titles add `mangohud %command%` to that game's launch options. Disable
> on a single game with `MANGOHUD=0 %command%`.

---

## Performance profile while a game runs

`game-performance` is a CachyOS wrapper that holds power-profiles-daemon's `performance` profile
(and blocks sleep) for as long as the wrapped command runs. Putting `game-performance %command%`
into every game's launch options works, but has to be redone for each new game.

`easy-switch install` enables `steam-game-performance.service` instead: while any Steam game is
running it holds the performance profile, and releases it when the last game exits. No launch
options needed, so keep them clean (`steam-clean-launch-options` removes old wrappers; Steam must
be closed).

```bash
watch -n1 powerprofilesctl get
# 'performance' while a game runs, back to balanced on exit
```

---

## Steam Controller (2026) — do NOT enable `PROTON_ENABLE_WAYLAND` with Proton-CachyOS

**Symptom:** with the new **Steam Controller (2026)** + wireless puck
(`28de:1304`) and `PROTON_ENABLE_WAYLAND=1` in `gaming.conf`, most Proton games
(Sifu, Sonic Racing Crossworlds, Tape to Tape) get double inputs and back-paddle
mappings stop working. Death Stranding 2 works because it uses the Steam Input
API directly.

**Why:** Proton-CachyOS preemptively disables Steam Input under native Wayland.
In `/usr/share/steam/compatibilitytools.d/proton-cachyos-slr/proton`:

```python
self.check_environment("PROTON_ENABLE_WAYLAND", "wayland")    # line ~1882
...
if "wayland" in self.compat_config and "WAYLAND_DISPLAY" in self.env:    # ~2125
    ...
    if "PROTON_NO_STEAMINPUT" not in self.env:
        self.env["PROTON_NO_STEAMINPUT"] = "1"
        # ...also DELETES SDL_GAMECONTROLLER_IGNORE_DEVICES,
        #          SteamVirtualGamepadInfo,
        #          SDL_GAMECONTROLLER_ALLOW_STEAM_VIRTUAL_GAMEPAD
```

When the Wayland flag is set, Proton-CachyOS forces `PROTON_NO_STEAMINPUT=1`
*and* strips the env vars Steam uses to hand the virtual gamepad to SDL/Wine.
Wine then reads `/dev/hidraw*` directly (visible as `winedevice.exe` opening
hidraw nodes alongside Steam), the game's SDL sees a duplicate controller, and
Steam Input's mappings (which live on the virtual gamepad it can no longer
hand off) never reach the game.

**SteamOS doesn't hit this** because (a) it uses Gamescope, not KWin, as the
compositor, and (b) it ships upstream Valve Proton, which doesn't have the
Proton-CachyOS Wayland auto-disable block.

**Fix on this machine:** leave `PROTON_ENABLE_WAYLAND` *unset* in `gaming.conf`
(commented out). Proton uses XWayland for the game, Steam Input keeps full
control of the controller, doubles and back-button issues disappear. Trade-off:
no native-Wayland HDR/latency for Proton games. The Steam Overlay also works
again (it was broken by Wayland mode anyway).

If you ever want native-Wayland-for-Proton back, the SteamOS-equivalent path
is to wrap each game in Gamescope:

```
gamescope -W 2560 -H 1440 -f -- game-performance %command%
```

That puts the game inside Gamescope's own Wayland compositor (which is what
SteamOS does), so the Proton-CachyOS auto-disable still fires but the
controller integration works because Gamescope behaves like SteamOS expects.
Not currently in use here — documented for the next attempt.

> **Diagnostic tool used to identify this:** `~/.local/bin/sc-debug-monitor`
> snapshots hidraw consumers and gamepad-class evdev devices every 2 seconds.
> When Wayland mode was active, `winedevice.exe` showed up opening all five
> puck hidraw nodes alongside `steam` — that's the duplicate input path. After
> removing the Wayland flag, only `steam` holds them.

> **Earlier red herring:** there was a `/etc/udev/rules.d/72-steam-controller.rules`
> that locked the puck's evdev keyboard/mouse aliases to root-only. It worked
> at the file-permission level but wasn't load-bearing for the doubling, which
> came from Wine's hidraw passthrough, not from the puck's lizard-mode evdev.
> Rule was removed.

---

## SSH keys for GitHub and Codeberg

Generate separate keys for each service:

```bash
ssh-keygen -t ed25519 -C "you@example.com" -f ~/.ssh/id_ed25519_github
ssh-keygen -t ed25519 -C "you@example.com" -f ~/.ssh/id_ed25519_codeberg
```

Create `~/.ssh/config`:

```
Host github.com
    HostName github.com
    User git
    IdentityFile ~/.ssh/id_ed25519_github

Host codeberg.org
    HostName codeberg.org
    User git
    IdentityFile ~/.ssh/id_ed25519_codeberg
```

Add the public keys to each service:

```bash
cat ~/.ssh/id_ed25519_github.pub    # paste into GitHub
cat ~/.ssh/id_ed25519_codeberg.pub  # paste into Codeberg
```

- **GitHub**: github.com → Settings → SSH and GPG keys → New SSH key → set Key type to **Authentication Key** → paste key
- **Codeberg**: codeberg.org → Settings → SSH Keys → Add Key → paste key

Test the connections:

```bash
ssh -T git@github.com
ssh -T git@codeberg.org
```

Always clone using SSH URLs (not HTTPS):

```bash
git clone git@codeberg.org:<you>/<repo>.git
git clone git@github.com:<you>/<repo>.git
```

---

## KDE Wallet auto-unlock with auto-login

If using auto-login, KDE Wallet will prompt for its password on every boot unless you
set a blank wallet password:

```bash
kwalletmanager5 --show
# Right-click kdewallet → Change Password → leave both fields blank → OK
```