# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A small, portable CLI for switching KDE Plasma display + audio configurations from a single TOML config. One repo clones onto any KDE machine; per-host data lives in `~/.config/easy-switch/config.toml`, never in the repo.

## Layout

- [easy-switch](easy-switch) — the Python CLI (no extension; the symlink in `~/.local/bin` is what users invoke). Runs under Python 3.11+ (uses stdlib `tomllib`). No third-party deps.
- [install.sh](install.sh) — symlinks the script into `~/.local/bin` and seeds `~/.config/easy-switch/`. Idempotent; safe to re-run.
- [examples/](examples/) — starter `config.toml`s for the two real setups (`basement.toml`, `living-room.toml`). These are documentation, not loaded at runtime.
- [basement/](basement/), [living-room/](living-room/) — **legacy** bash scripts the CLI replaces. Kept for reference until the user has migrated their KDE shortcuts. The example TOMLs reproduce their behavior exactly; if you change one, update the other or note the divergence.

## How the CLI works

`easy-switch <mode>` is **probe → validate → mutate**, in that order — the ordering is load-bearing for atomic failure:

1. `parse_outputs()` runs `kscreen-doctor -o` (read-only) and extracts per-output `connected`, `enabled`, `primary` (`priority 1`), starred mode, geometry, rotation. ANSI is stripped first.
2. If the mode's `requires_any` is non-empty and none of those outputs is connected, **nothing happens** — no kscreen reset, no display change, no audio change. Exit 2. The only exception is `audio_only_fallback = true`, which is an explicit per-mode opt-in to still call `pactl set-default-sink` when the display is missing.
3. Only after the requirements pass does the CLI call `kscreen-doctor configure` to refresh state, then re-probe (a display can vanish between probe and reset — handled).
4. Builds **up to two** kscreen-doctor invocations via `build_kscreen_commands()`: one for all enables (with their `.primary`/`.mode`/`.position`/`.rotation` flags) and one for all disables. They run sequentially with a `KSCREEN_SETTLE_SECONDS` (1.0s) sleep between. **Do not collapse this back into one command.** Combining enable+disable in a single kscreen-doctor call fails with `Failure: No such entity` when the primary display switches mid-command — confirmed on the basement couch transition (DP-3 primary → HDMI-A-1 primary). The legacy bash scripts split for the same reason. The "one combined command" lesson from `legacy/basement/all-mode.sh` still applies *within* the enable batch (multiple outputs going on together) — it does not apply across the enable/disable boundary.
5. Between the enable batch and the disable batch, `verify_output_alive()` (DPMS-based, in [easy-switch](easy-switch)) checks that kscreen actually flipped `enabled=true` with the expected mode and that DRM `dpms` reads `On`. This catches the *cooperative* failure modes (a connector that errored mid-apply, a mode that didn't take). It explicitly **does not** try to catch "TV is in standby" — see the dead-end note below.
6. If any step fails (non-zero exit) or the verifier rejects, the CLI aborts **before** changing audio. `pactl` is only invoked on a successful display apply.
7. `notify-send` for the final state.

## Dead end: detecting a powered-off TV

This was investigated extensively over multiple sessions and the conclusion is: **on at least NVIDIA proprietary + LG HDMI, the OS literally cannot tell.** Don't reintroduce a `verify_eld`-style check expecting it to work — the four state-pairs we'd need to distinguish look identical to every readable signal:

| TV state | `connected` | `/sys/.../dpms` | ELD pre-enable | ELD post-enable |
|---|---|---|---|---|
| On, signal flowing | ✓ | On | populated | populated |
| **On, no signal yet** | ✓ (lies) | n/a (disabled) | **empty** | populated |
| **Standby, no signal** | ✓ (lies) | n/a (disabled) | **empty** | populated (CEC wakes it) |
| Unplugged | disconnected | n/a | empty | n/a |

The two bold rows are the ones a user wants distinguished, and there is no software-only discriminator without CEC. NVIDIA's proprietary driver doesn't expose `/dev/cec*`, so `cec-ctl` isn't an option here. The signals tried and rejected:

- `kscreen-doctor -o`: caches `connected` from EDID.
- `/sys/class/drm/.../status`, `.../enabled`: same cache.
- `/sys/class/drm/.../dpms`: reflects what userspace asked KMS to do, not what the panel did.
- `/proc/asound/.../eld#* monitor_present`: only populates while HDMI signal is flowing on this hardware. The act of running `kscreen-doctor output.HDMI-A-1.enable` wakes the TV's HDMI subsystem (CEC One-Touch-Play, even with LG Quick Start disabled), so a post-enable check catches that transient wake. A pre-enable check is empty in both "TV off" and "TV on but not yet signaling," which broke `easy-switch couch` when the user had genuinely turned the TV on but hadn't switched its input yet.

The accepted behavior: `couch` always applies when requested; if the TV is off the user runs a recovery mode via their second keyboard shortcut. The README has a Limitations section documenting this. **If you're tempted to take another pass at this, ask the user about their hardware first — the answer may differ on AMD/Intel iGPUs that expose CEC.**

All subprocess invocations go through a small `run()` helper that converts `FileNotFoundError` (binary missing) into a clean `die()` message; `CalledProcessError` is caught around the apply and audio steps specifically.

`--dry-run` skips the reset and the apply, prints the would-be commands, makes no changes. `--list` enumerates modes. `EASY_SWITCH_CONFIG=…` overrides the config path.

## The `add` / `remove` subcommands

`easy-switch add <name>` snapshots the host's current state into a named mode:

1. Calls `parse_outputs()` to capture every output's current settings (mode, position, rotation, primary, enable/disable).
2. Calls `detect_sinks()` (`pactl list sinks` long form) to list audio sinks with their Description fields, and prompts for one.
3. Prompts only for things that can't be detected: free-text description, `requires_any` (default: primaries, with all enabled outputs offered as alternatives), and `audio_only_fallback`.
4. Always sets `strict = true` on the new mode so a display that's plugged in *after* the snapshot was taken still gets disabled by this mode. (See "Config schema" below for what strict does.)
5. Writes the result back into `~/.config/easy-switch/config.toml`:
   - **No file yet:** create with a host-stamped header + the new block.
   - **File exists, mode doesn't:** append the new block; other modes and comments untouched.
   - **Mode already exists:** prompts to confirm overwrite, then splices the new block in place of the old one (text-level replacement via `replace_mode_block`) so sibling modes survive.

`easy-switch remove <name>` (or `rm`) deletes a mode block by name. Prompts to confirm unless `--force`. Uses `delete_mode_block` to splice out the `[modes.<name>]` table and all its `[modes.<name>.outputs.…]` subtables, preserving sibling modes and surrounding comments.

TOML writing is hand-rolled (`emit_value` + `emit_mode_block`) because `tomllib` is read-only and the schema is fixed and tiny. Don't pull in a third-party TOML writer for this.

The snapshot deliberately *omits* outputs that are disconnected — the wizard's mental model is "set up what you want, then capture it." If you need to define a mode for hardware that isn't currently plugged in, hand-edit the TOML.

## Config schema

See the README for the full table. Key invariants when editing the CLI or examples:

- An output entry with `enable = true` that isn't connected is **silently skipped**, not an error — this is how optional displays (e.g. basement DP-2 portrait) coexist with required ones (DP-3).
- `requires_any` is "at least one of"; `all-mode` exploits this to apply whatever's connected from the three-monitor set.
- `audio_only_fallback = true` is the living-room "partial mode" behavior — keep audio switching even when no display is present.
- `strict = true` makes the mode disable any *currently-connected* output that isn't listed under `[modes.<name>.outputs.…]`. This closes the wizard-blind-spot where an output absent at snapshot time wouldn't get a rule and would silently stay enabled when later plugged in. The wizard sets it by default; the example configs set it too. Without `strict`, only outputs with an explicit `enable = false` entry get disabled.

## Running and testing

- No build, no tests, no linter. The script is exercised by running it.
- `python3 ./easy-switch --help` and `EASY_SWITCH_CONFIG=examples/basement.toml python3 ./easy-switch --list` both work without any installation and are the quickest smoke checks.
- `EASY_SWITCH_CONFIG=examples/basement.toml ./easy-switch --dry-run desk` is safe to run on any host — it shells out to `kscreen-doctor -o` (read-only) and prints the commands it would run.
- Real behavioral verification still requires the actual hardware; there is no way to fake `kscreen-doctor` apply.

## Hardware-specific constants

Output names, modes, positions, and sink IDs are hardware-specific and live in `~/.config/easy-switch/config.toml` per host — the user's live config is the source of truth for what their machine currently does. The files in [examples/](examples/) are *starter templates* for fresh installs (and the basement template is roughly the user's intended full setup with DP-2 portrait, which their current live config may or may not include depending on what's plugged in at snapshot time). If something durable changes on a host (e.g. the user picks a different audio profile, like the May 2026 switch from Arctis `pro-output-0` → `analog-stereo`), update the matching `examples/*.toml` too so a fresh `cp` reproduces the new preference.
