# Minecraft Java in Gaming Mode (Prism Launcher → Springfield server)

One Steam library tile, **Minecraft**, that starts Prism Launcher's `Main`
instance and joins the house server directly, with a controller, shaders,
and the game window matched to whichever screen Gaming Mode is on. Set up on
**lisa** first, then **bonestorm** (2026-11-15). Builds on [GAMING-MODE.md](GAMING-MODE.md).

The one host file is [`gaming-mode/minecraft/fullscreen-by-session.sh`](gaming-mode/minecraft/fullscreen-by-session.sh)
(live copy: `~/minecraft/fullscreen-by-session.sh`; keep the two identical).

## The pieces

- **Server**: Fabric 26.3 on frinkahedron (192.168.10.7), port 25565, offline
  mode, auto-pauses when empty (the first join can take a few seconds). Use
  **`frinkahedron.lan`**: the short name doesn't resolve on lisa or bonestorm
  (no `lan` search domain). Check with `getent hosts frinkahedron`.
- **Launcher**: Prism Launcher from the distro repo (`pacman -S prismlauncher`).
  Never a "cracked"/"unlocked" fork. Prism manages Java itself.
- **Pack**: the house `Main.mrpack` (Minecraft 26.3, Fabric Loader 0.20.1, Fabric
  API, Sodium, Iris, Controlify + YACL, Lithium, Complementary Reimagined).
  Import it with `prismlauncher --import Main.mrpack`, instance name exactly
  `Main`. Don't add or swap mods. The `.mrpack` is only an index; Prism fetches
  the jars from the Modrinth CDN and checks their hashes.
- **Accounts**: add the owner's Microsoft account (Prism only allows offline
  accounts while one is present), then an **offline** account per PC as the
  default. Offline because the server doesn't check sign-ins, and an expired
  Microsoft token would stop the launch with a sign-in dialog that a controller
  can't get past in Gaming Mode. Names must differ per PC to play at the same
  time: lisa `jameyz`, bonestorm `tonyz`. The offline server keys player data by
  name, so keep the name to keep the inventory.

## Setup on a host

1. Import the pack (above), add the accounts in Prism's GUI, and set the
   offline one as default. Never edit `accounts.json` by hand (it holds the
   Microsoft token).
2. **Server list**: `instances/Main/minecraft/servers.dat` (uncompressed NBT)
   with one entry, name `Springfield`, ip `frinkahedron.lan:25565`.
3. **Shaders**: `instances/Main/minecraft/config/iris.properties`:
   `enableShaders=true`, `shaderPack=ComplementaryReimagined_r5.9.3.zip`.
4. **Pre-launch command**: with Prism closed, append to `instances/Main/instance.cfg`:
   ```
   OverrideCommands=true
   PreLaunchCommand=/home/<user>/minecraft/fullscreen-by-session.sh
   ```
   Prism (11.x) keeps running in the background after its window closes.
   Check `pgrep prismlauncher` before editing its files.
5. **Steam shortcut**: with Steam fully closed (`steam -shutdown`, then check
   `ps -eo comm | grep -i steam`; `pgrep -f steamwebhelper` matches its own
   command line), add a `shortcuts.vdf` entry: AppName `Minecraft`,
   Exe `"/usr/bin/prismlauncher"`, LaunchOptions `-l Main -s frinkahedron.lan:25565`.
   AppID = `crc32(Exe + AppName) | 0x80000000`, stored as a signed int32
   (bonestorm: 3212112756 / -1082854540). Back up every Steam file first.
   Set `icon` here too, and add the library art (see "Library artwork" below).
6. **Steam Input on**: in `userdata/<id>/config/localconfig.vdf`, under
   `UserLocalConfigStore/apps`, add `"<appid unsigned>" { "UseSteamControllerConfig" "2" }`.
7. **Gamepad layout** for every controller family the house uses: in
   `steamapps/common/Steam Controller Configs/<id>/config/configset_controller_<type>.vdf`
   add `"minecraft" { "template" "<file>" }` (key = lower-case shortcut name):
   - neptune, triton (Steam Controller 2026): `controller_neptune_gamepad_joystick.vdf`
   - xboxone: `controller_xboxone_gamepad_joystick.vdf`
   - xbox360 (also the 8BitDo Pro 3 in X-input mode): `controller_xbox360_gamepad_joystick.vdf`
   - 8bitdo, generic: `controller_generic_gamepad_joystick.vdf`

   Nothing in them goes to keyboard or mouse. The neptune template defines
   trackpad-mouse groups but they're inactive in its preset.
8. **Test**: desktop launch (joins, shaders, controller), then Gaming Mode on
   each screen. The game log is `instances/Main/minecraft/logs/latest.log` (grep
   with `-a`, it contains binary bytes).

## Library artwork (SteamGridDB)

The art is kept once in the shared Steam art library on the NAS,
`/mnt/games/steam-art/minecraft/` (`game.json` = `{"shortcut": "Minecraft"}`),
and goes onto a PC with `gaming-mode/steam-art/steam-art.py apply minecraft`.
See [gaming-mode/steam-art/README.md](gaming-mode/steam-art/README.md) for the
mount and for adding other games. The images aren't in this repo. Before the
library existed (2026-11-19) they were copied by hand from bonestorm's
`~/Pictures/steamgriddb/minecraft/` to lisa. Steam reads them from
`userdata/<steamid>/config/grid/`, named by the shortcut's unsigned AppID
(3212112756 on every PC, since Exe + AppName are the same):

- `cover.png` (600x900) → `<appid>p.png` (library capsule)
- `widecover.png` (920x430) → `<appid>.png` (wide capsule / recent games)
- `background.png` (1920x620) → `<appid>_hero.png`
- `logo.png` → `<appid>_logo.png`
- `icon.png` (256x256): not in `grid/`. It goes in the shortcut's `icon`
  field in `shortcuts.vdf` (full path), so set it with Steam closed, like step 5.

Do it for **every Steam account on the PC**: lisa has two (103883330 and
1181233838), and each has its own `grid/` folder and its own `shortcuts.vdf`.
Grid files can be copied while Steam runs; they show after a Steam restart.

**SteamGridDB icons are `.ico`; Steam needs a real PNG.** Renaming
`icon.ico` to `icon.png` isn't enough: `file icon.png` still says "MS Windows
icon resource" and Steam shows nothing. Convert the largest frame instead
(`identify icon.ico` lists them, the 256x256 one is usually `[5]`):
```
magick 'icon.ico[5]' icon.png
```

On lisa (Plasma desktop), Steam runs as the user unit `steam.service`:
`systemctl --user stop steam.service`, edit, `systemctl --user start steam.service`.
Backups from 2026-11-19: `shortcuts.vdf.bak-20261119` next to each file.

## Why windowed, and at what size

Under gamescope, Minecraft 26.3 in **exclusive fullscreen** stalls its SDL window
every frame (`Failed to synchronize SDL window` in the log, ~10 fps). The
pre-launch script fixes this per launch:

- **Gaming Mode** (`$GAMESCOPE_WAYLAND_DISPLAY` set or `XDG_CURRENT_DESKTOP=gamescope`):
  `options.txt` gets `fullscreen:false` plus `overrideWidth`/`overrideHeight` =
  the native mode of the screen gamescope is driving. That's the only DRM
  connector with `enabled` = `enabled` in sysfs, and gamescope uses its
  preferred mode (first line of `modes`). Fallbacks: gamescope's
  `drm: selecting mode WxH@R` journal line, then 2560x1440.
- **Desktop**: `fullscreen:true`, overrides reset to 0.

So every screen renders at its native resolution with no scaling.
bonestorm: desk DP-3 2560x1440@165 (VRR 48–165), TV HDMI-A-1 3840x2160@60 (no VRR).
Both verified in the gamescope journal and the game log, with zero SDL stalls.
(lisa's copy of the script predates this version and used a fixed 2560x1440.)

## Pitfalls (don't repeat)

1. **Don't size the window from the X root (`xdpyinfo`).** When a game starts,
   Steam sets gamescope's game Xwayland (server #1) to Steam's *Maximum game
   resolution* (`localconfig.vdf` → `Gamescope/GameResolutionGlobal`; bonestorm
   `3840x2160`), not to the panel. On the 1440p desk panel Minecraft rendered
   4K and was scaled down: 99% GPU, under 150 fps. The panel size from DRM sysfs
   fixed it. Games with their own resolution setting aren't affected; games
   that follow the "desktop" size are.
2. **Never round-trip Steam's text VDFs through python-vdf** (`vdf.load`/`vdf.dumps`).
   It escapes apostrophes (`Baldur's` → `Baldur\'s`) and rewrites the tab
   layout. Insert lines as text, then check by parsing old and new and
   comparing. The binary `shortcuts.vdf` via `vdf.binary_dumps` is fine.
3. **Expected log noise with an offline account**: `401` on
   `/player/attributes`, Realms `Failed to parse into SignedJWT`, narrator
   `libflite.so` not found. All harmless.
4. Controlify can log `No controllers found` at startup and still work once
   a controller connects.

## Shaders

Shader packs aren't mods: drop the zip into `instances/Main/minecraft/shaderpacks/`
(client-side only, nothing on the server), pick one under Options → Video
Settings → Shader Packs (**O** opens it, **K** toggles shaders). Iris remembers
the choice in `iris.properties`; the pre-launch script doesn't touch it.
bonestorm also has, all from Modrinth for 26.3 with hashes checked:
Complementary Unbound r5.9.3, Photon v1.4, Bliss 2.1.2, FoxyShader 1.3.3-beta
(software ray tracing, best-looking on bonestorm but with dips; fine on the VRR
desk panel). Real RTX-hardware ray tracing on Java needs the Vulkanite mod
(+ packs like Dirt RT), which isn't out for 26.3 and would be a mod change to the pack.

## Parked

- **60 fps cap on the TV only**: have the script write `maxFps:60` when the
  driven connector is the TV, saving the desk value to restore it at the desk.
  Steam's frame limit can't do this per screen, and vsync under gamescope is
  untested. At 4K the GPU is at 99% while holding 60.
