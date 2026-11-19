#!/usr/bin/env python3
"""Install SteamGridDB art from the shared library into every Steam account on this PC.

Library: /mnt/games/steam-art/<game>/ (NAS plex_media/games, see mount-nas-games.sh)
  game.json       {"shortcut": "Minecraft"}  - a non-Steam shortcut, by its Steam name
               or {"appid": 1086940}         - a real Steam game
  cover.png       600x900   -> grid/<appid>p.png      (library capsule)
  widecover.png   920x430   -> grid/<appid>.png       (wide capsule)
  background.png  1920x620  -> grid/<appid>_hero.png
  logo.png                  -> grid/<appid>_logo.png
  icon.png / icon.ico       -> shortcuts.vdf "icon" (shortcuts only; Steam closed)

  steam-art.py list
  steam-art.py apply minecraft [--dry-run]
  steam-art.py apply --all

Grid files can be written while Steam runs (they show after a restart). The icon
lives in shortcuts.vdf, which Steam rewrites while running, so it's only set with
Steam closed. The icon is copied to ~/Pictures/steamgriddb/<game>/icon.png, so it
still shows when the NAS isn't mounted. A .ico is converted to a real PNG
(largest frame) with ImageMagick; a renamed .ico doesn't work.
"""
import argparse, glob, json, os, shutil, subprocess, sys, time

LIB = os.environ.get("STEAM_ART_LIB", "/mnt/games/steam-art")
STEAM = os.path.expanduser(os.environ.get("STEAM_ROOT", "~/.local/share/Steam"))
LOCAL = os.path.expanduser("~/Pictures/steamgriddb")
GRID = {"cover.png": "{}p.png", "widecover.png": "{}.png",
        "background.png": "{}_hero.png", "logo.png": "{}_logo.png"}
PNG = b"\x89PNG\r\n\x1a\n"


def steam_running():
    if os.environ.get("STEAM_ART_TEST_STEAM_CLOSED"):  # tests against a fake STEAM_ROOT only
        return False
    return subprocess.run(["pgrep", "-x", "steam"], capture_output=True).returncode == 0


def is_png(path):
    with open(path, "rb") as f:
        return f.read(8) == PNG


def same(a, b):
    if not os.path.exists(b) or os.path.getsize(a) != os.path.getsize(b):
        return False
    with open(a, "rb") as fa, open(b, "rb") as fb:
        return fa.read() == fb.read()


def icon_source(gdir):
    """A real PNG icon for the game, converting a .ico (or a renamed .ico) if needed."""
    for name in ("icon.png", "icon.ico"):
        p = os.path.join(gdir, name)
        if os.path.exists(p) and is_png(p):
            return p, None
    for name in ("icon.ico", "icon.png"):
        p = os.path.join(gdir, name)
        if os.path.exists(p):
            return None, p  # needs converting
    return None, None


def convert_ico(src, dst, dry):
    if dry:
        return True
    tool = shutil.which("magick") or shutil.which("convert")
    if not tool:
        print("  ! icon is .ico and ImageMagick isn't installed - skipped")
        return False
    out = subprocess.run(["identify", "-format", "%[scene] %w\n", src],
                         capture_output=True, text=True).stdout.split("\n")
    frames = sorted((int(w), int(s)) for s, w in (l.split() for l in out if l.strip()))
    best = frames[-1][1] if frames else 0
    subprocess.run([tool, f"{src}[{best}]", dst], check=True)
    return is_png(dst)


def accounts():
    return sorted(glob.glob(os.path.join(STEAM, "userdata", "[0-9]*", "config")))


def apply(game, dry):
    import vdf
    gdir = os.path.join(LIB, game)
    meta = json.load(open(os.path.join(gdir, "game.json")))
    print(f"== {game}")
    running = steam_running()

    local_icon = None
    if meta.get("shortcut"):
        png, ico = icon_source(gdir)
        if png or ico:
            local_icon = os.path.join(LOCAL, game, "icon.png")
            if not dry:
                os.makedirs(os.path.dirname(local_icon), exist_ok=True)
            if png and not same(png, local_icon):
                print(f"  icon -> {local_icon}")
                if not dry:
                    shutil.copy2(png, local_icon)
            elif ico and os.path.exists(local_icon) and is_png(local_icon) \
                    and os.path.getmtime(local_icon) >= os.path.getmtime(ico):
                pass  # converted on an earlier run
            elif ico:
                print(f"  icon {os.path.basename(ico)} is not a PNG - converting -> {local_icon}")
                if not convert_ico(ico, local_icon, dry):
                    local_icon = None

    for cfg in accounts():
        uid = cfg.split(os.sep)[-2]
        sc_path = os.path.join(cfg, "shortcuts.vdf")
        appid, data, entry = meta.get("appid"), None, None
        if meta.get("shortcut"):
            if not os.path.exists(sc_path):
                print(f"  {uid}: no shortcuts - skipped"); continue
            data = vdf.binary_loads(open(sc_path, "rb").read())
            for v in data.get("shortcuts", {}).values():
                if v.get("AppName") == meta["shortcut"]:
                    entry = v
            if entry is None:
                print(f"  {uid}: no shortcut named {meta['shortcut']!r} - skipped"); continue
            appid = entry["appid"] & 0xFFFFFFFF
        grid = os.path.join(cfg, "grid")
        done = []
        for src, pat in GRID.items():
            s = os.path.join(gdir, src)
            if not os.path.exists(s):
                continue
            d = os.path.join(grid, pat.format(appid))
            if not same(s, d):
                done.append(os.path.basename(d))
                if not dry:
                    os.makedirs(grid, exist_ok=True)
                    shutil.copy2(s, d)
        print(f"  {uid}: appid {appid}: " + (", ".join(done) + (" (dry run)" if dry else "") if done else "grid up to date"))
        if entry is not None and local_icon and entry.get("icon") != local_icon:
            if running:
                print(f"  {uid}: icon NOT set - Steam is running; quit Steam and run again")
            elif dry:
                print(f"  {uid}: would set icon {local_icon}")
            else:
                shutil.copy2(sc_path, sc_path + ".bak-" + time.strftime("%Y%m%d-%H%M%S"))
                entry["icon"] = local_icon
                open(sc_path, "wb").write(vdf.binary_dumps(data))
                chk = vdf.binary_loads(open(sc_path, "rb").read())
                ok = any(v.get("AppName") == meta["shortcut"] and v.get("icon") == local_icon
                         for v in chk["shortcuts"].values())
                print(f"  {uid}: icon set" if ok else f"  {uid}: ! icon write did not verify")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    a = sub.add_parser("apply")
    a.add_argument("game", nargs="*")
    a.add_argument("--all", action="store_true")
    a.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if not os.path.isdir(LIB):
        sys.exit(f"{LIB} not found - is the NAS mounted? (mount-nas-games.sh)")
    games = sorted(d for d in os.listdir(LIB) if os.path.exists(os.path.join(LIB, d, "game.json")))
    if args.cmd == "list":
        for g in games:
            print(g, json.load(open(os.path.join(LIB, g, "game.json"))))
        return
    todo = games if args.all else args.game
    if not todo:
        sys.exit("name a game or use --all")
    for g in todo:
        apply(g, args.dry_run)


if __name__ == "__main__":
    main()
