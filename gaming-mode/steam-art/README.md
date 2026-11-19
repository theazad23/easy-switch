# Steam art library (SteamGridDB, shared on the NAS)

Custom library art for Steam games and non-Steam shortcuts, kept once on the NAS
and installed on each PC (bonestorm, lisa) into **every Steam account** there.

- **Library**: NAS `plex_media/games/steam-art/<game>/`, mounted on each PC at
  `/mnt/games/steam-art` (automount, `nofail`, so a PC without the NAS still boots).
- **One-time per PC**: `sudo ./mount-nas-games.sh` - asks for the NAS SMB login,
  stores it root-only in `/etc/samba/nas-credentials`, creates the folder on the
  NAS if needed, adds the `/etc/fstab` line (backs up fstab first).
- **Install art**: `./steam-art.py apply <game>` (or `--all`, `--dry-run`; `list`).
  Grid art goes in while Steam runs and shows after a Steam restart. The icon of a
  non-Steam shortcut is set only with Steam closed (it lives in `shortcuts.vdf`,
  which Steam overwrites while running), so quit Steam and run it again for that.
  Every write to `shortcuts.vdf` leaves a timestamped `.bak-*` beside it.

## Adding a game

Make `/mnt/games/steam-art/<game>/` with:

- `game.json`: `{"shortcut": "Minecraft"}` for a non-Steam shortcut (its exact
  Steam name; the AppID is read from each account's `shortcuts.vdf`), or
  `{"appid": 1086940}` for a game bought on Steam (the number in its store URL).
- whatever of these SteamGridDB has (all optional):
  - `cover.png` 600x900 - library capsule → `grid/<appid>p.png`
  - `widecover.png` 920x430 - wide capsule / recent games → `grid/<appid>.png`
  - `background.png` 1920x620 - hero → `grid/<appid>_hero.png`
  - `logo.png` - logo over the hero → `grid/<appid>_logo.png`
  - `icon.ico` or `icon.png` - shortcut icon (shortcuts only; Steam games keep theirs)

Then `./steam-art.py apply <game>` on each PC.

**SteamGridDB icons are `.ico`, and Steam needs a real PNG.** Renaming the file
isn't enough (`file icon.png` still says "MS Windows icon resource" and Steam
shows nothing). Just drop the `.ico` in: the tool converts its largest frame with
ImageMagick into `~/Pictures/steamgriddb/<game>/icon.png` - a local copy, so the
icon still shows when the NAS isn't mounted.

## Testing

Use a throw-away library and a fake Steam folder: `STEAM_ART_LIB`, `STEAM_ROOT`
and `HOME` pointed at temp dirs, plus `STEAM_ART_TEST_STEAM_CLOSED=1` to exercise
the icon write while the real Steam runs. Never set that last one against the
real Steam folder.
