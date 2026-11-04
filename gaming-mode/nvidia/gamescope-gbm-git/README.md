# gamescope-gbm-git: gamescope master + NVIDIA GBM scan-out patch

**Problem it fixes (bonestorm, RTX 4080 SUPER → LG TV 4K60):** in Gaming Mode, a random
~50–80 % of starts show flickering squares (filled left→right, top→down, from a varying point
on) and sometimes torn/offset/discoloured blocks. Upstream: ValveSoftware/gamescope
[#2309](https://github.com/ValveSoftware/gamescope/issues/2309) (same hardware),
[#1593](https://github.com/ValveSoftware/gamescope/issues/1593), [#2333](https://github.com/ValveSoftware/gamescope/issues/2333).
NVIDIA (cubanismo, #1593): the display engine can't scan out non-contiguous memory; gamescope
allocates scan-out images with Vulkan, which can't ask for display-capable memory, so at 4K they
are sometimes non-contiguous. KWin allocates with GBM → the desktop is always fine.

**Fix:** allocate the scan-out buffers with GBM. The patch comes from
[farnoy/gamescope `nvidia-gbm-wayland`](https://github.com/farnoy/gamescope/tree/nvidia-gbm-wayland)
(based on NightHammer1000's `poc/gamescope-gbm-route`), 14 commits rebased onto upstream master
and squashed into `0001-nvidia-gbm-scanout.patch`. It adds a convar `drm_gbm_scanout`
(default off); `~/.config/gamescope/scripts/50-nvidia-tv-fix.lua` turns it on (and is a no-op on
unpatched gamescope).

**Tested 2026-11-04:** alternating rounds, same conditions: stock gamescope-git 4/6 bad,
GBM 0/6 bad; confirmation run with GBM as default 0/12 bad ; installed package 0/6 (0/24 total). Known quirks: ~10 s to exit (systemd SIGKILLs it, harmless), logs
`GBM allocation failed for 32x32` (cursor-size buffers), needs LuaJIT-safe scripts (no `warn()`).

## Files

| File | What |
|---|---|
| `PKGBUILD` | AUR gamescope-git recipe + the patch. Provides/conflicts `gamescope`, `gamescope-git` |
| `0001-nvidia-gbm-scanout.patch` | the GBM change, against upstream master |
| `update.sh` | build + install from latest upstream (`makepkg -sif`; asks for sudo) |
| `refresh-patch.sh` | re-base the patch onto newer upstream when it stops applying (git only) |

## Updating (manual, when you want newer gamescope)

```sh
cd ~/Projects/easy-switch/gaming-mode/nvidia/gamescope-gbm-git
./update.sh --check     # how far upstream has moved since your build
./update.sh             # pull upstream master, apply patch, build, install
```

`pacman -Syu` will **not** update it (it's a local package), and it won't be replaced by the repo
`gamescope`/`gamescope-git` either, since it provides both.

## When the patch stops applying

`update.sh` stops with "0001-nvidia-gbm-scanout.patch no longer applies". Then:

```sh
./refresh-patch.sh      # rebases branch gbm-on-master in ~/src/gamescope-gbm onto upstream
```

- Clean rebase → it re-exports the patch; run `./update.sh` again.
- Conflict → git lists the files. Edit them so both upstream's change and the GBM change survive
  (on 2026-11-04 the only conflict was `WaylandBackend.cpp`, upstream's early return vs the
  fork's `OnCompositorAcquire()`: keep the early return first, then the acquire), then
  `git -C ~/src/gamescope-gbm add <files> && git -C ~/src/gamescope-gbm rebase --continue`,
  and run `./refresh-patch.sh` again.
- Also check whether the fork has new fixes: `git -C ~/src/gamescope-gbm fetch origin` and
  compare `origin/nvidia-gbm-wayland`.

## When to drop it

- NVIDIA said they'd add a gamescope-specific driver workaround. After a driver update, test stock
  gamescope (`sudo pacman -S gamescope-git`, then `gaming-mode-cycle 12 20 0` + the form) —
  if it's clean, go back to the repo package.
- Or if upstream gamescope merges GBM scan-out (watch #2309).

## Going back to stock

```sh
sudo pacman -S gamescope-git     # replaces gamescope-gbm-git
```
The Lua script ignores `drm_gbm_scanout` when the binary doesn't have it.
