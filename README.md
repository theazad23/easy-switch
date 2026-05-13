# Easy Switch

KDE-only CLI for switching display + audio modes. Define modes in a TOML config; trigger them with `easy-switch <mode>` (bind that to a KDE Custom Shortcut).

## Install

```sh
./install.sh
```

The install script symlinks [easy-switch](easy-switch) into `~/.local/bin`. Per-host config lives at `~/.config/easy-switch/config.toml` and is **not** tracked in this repo — clone once, install once, configure per machine.

### Requirements

- KDE Plasma (5 or 6)
- Python 3.11+ (for `tomllib`)
- `kscreen-doctor`, `pactl` (PulseAudio/PipeWire), `notify-send`

## First-time setup on a new machine

Arrange your displays and audio the way you want using KDE's normal GUI (System Settings → Display, plus your sound applet). Then snapshot that arrangement into a named mode:

```sh
easy-switch add desk
```

The wizard detects every output kscreen-doctor sees (with current resolution, position, rotation, primary status), lists all pactl audio sinks, and asks you for the few things it can't figure out: a description, which sink to use, which displays are *required* for the mode, and whether to switch audio when those displays are missing. Then it writes a mode block into `~/.config/easy-switch/config.toml` — creating the file if needed, or merging into your existing one (other modes are preserved).

Rearrange and repeat for each named mode you want (`easy-switch add tv`, `easy-switch add couch`, etc.). Re-running `easy-switch add desk` will prompt before overwriting.

You can still hand-write or hand-edit configs — see [examples/](examples/) for two real setups.

## Usage

```sh
easy-switch desk             # apply the mode named "desk"
easy-switch add tv           # snapshot current state into a new mode "tv"
easy-switch remove tv        # delete the "tv" mode (prompts to confirm; --force to skip)
easy-switch --list           # list modes configured on this host
easy-switch --dry-run desk   # print the commands that would run, change nothing
```

`EASY_SWITCH_CONFIG=/path/to/other.toml easy-switch desk` overrides the config path — handy for testing.

## Limitations

**Detecting a powered-off TV is not possible** on at least NVIDIA + LG HDMI (and likely any setup without userspace CEC). With the HDMI cable still plugged in, every signal Linux exposes — kscreen `connected`, `/sys/class/drm/.../status`, `/sys/class/drm/.../dpms`, `/proc/asound/.../eld#*` — either lies (EDID is cached) or only flips when *signal is flowing*, not when the TV is on. The two states "TV in standby" and "TV on but not yet receiving signal" look identical to the OS. Without CEC we can't ask the TV "are you on?"

Practical workflow: if you bind `easy-switch couch` to a shortcut and hit it while the TV is off, your other displays go dark anyway — bind `easy-switch desk` (or whichever mode covers your other displays) to a second shortcut so the recovery is one keypress.

## Failure semantics

The apply path is **probe → validate → mutate**, so a failed precondition makes zero changes.

When `requires_any` outputs are not connected:

- **Default:** nothing changes — no display reconfigure, no audio switch, no kscreen-doctor commands run at all. Exit code 2.
- **`audio_only_fallback = true`** (per-mode opt-in): only the audio sink is switched. Used by the living-room modes so plugging in headphones works even with no monitor attached.

When `requires_any` passes but something fails mid-apply:

- Displays are reconfigured as an *enable batch* (the new outputs, with `.primary`/`.mode`/`.position`/`.rotation`) followed by a 1-second settle, then a *disable batch* (outputs being turned off). If the enable batch fails, the disable batch is skipped and audio is **not** changed. If the disable batch fails, audio is also skipped.
- If the audio sink change fails after a successful display apply, you get a "partial" notification — displays switched, audio didn't.

Every failure mode fires a `notify-send` desktop notification with a human-friendly message naming the affected output. Exit codes are 0 (success) / 2 (failure).

## Configuration

Each mode is a `[modes.<name>]` table in `~/.config/easy-switch/config.toml`:

| Key | Meaning |
| --- | --- |
| `description` | Free-text shown in `--list` and the success notification. |
| `requires_any` | List of output names; at least one must be connected for the mode to apply. Omit to always apply. |
| `strict` | If `true`, any currently-connected output **not** listed under `outputs` is disabled. Set by default by `easy-switch add`. Without it, a display plugged in after the snapshot was taken would stay on. |
| `audio` | `pactl` sink name to switch to. |
| `audio_only_fallback` | If `true` and `requires_any` is unmet, still switch audio. |
| `outputs.<NAME>` | Per-output settings (see below). |

Per-output keys (all optional except `enable`):

| Key | Effect |
| --- | --- |
| `enable = true` | Enable this output if it's connected. Not connected → silently skipped (so optional displays don't break the mode). |
| `enable = false` | Disable this output if it's connected. |
| `primary = true` | Make this the primary display. |
| `mode = "WxH@Hz"` | e.g. `"2560x1440@165"`. |
| `position = "X,Y"` | e.g. `"1440,560"`. |
| `rotation = "right"` | KDE rotation keyword (`normal`, `left`, `right`, `inverted`). |

### Finding the right names

- Display outputs: `kscreen-doctor -o`
- Audio sinks: `pactl list sinks short`

### Example

```toml
[modes.desk]
description = "DP-3 primary with DP-2 portrait"
requires_any = ["DP-3"]
audio = "alsa_output.usb-SteelSeries_Arctis_Nova_Pro_Wireless-00.pro-output-0"

[modes.desk.outputs.DP-3]
enable = true
primary = true
mode = "2560x1440@165"
position = "1440,560"

[modes.desk.outputs.DP-2]
enable = true
mode = "2560x1440@144"
rotation = "right"
position = "0,0"

[modes.desk.outputs.HDMI-A-1]
enable = false
```

Full starter configs for two real setups: [examples/basement.toml](examples/basement.toml), [examples/living-room.toml](examples/living-room.toml).

## KDE keyboard shortcuts

System Settings → Shortcuts → Custom Shortcuts:

1. Edit → New → Global Shortcut → Command/URL
2. Name it (e.g. "Easy Switch — Desk")
3. **Trigger** tab: pick a key combo
4. **Action** tab: command `easy-switch desk` (use the full path `~/.local/bin/easy-switch` if your shortcut runner doesn't pick up your shell PATH — KDE often doesn't)

Repeat per mode.

**Avoid `Ctrl+Alt+<arrow>` keys** — every direction is bound by default in Plasma (workspace navigation, activity switching, or kwin tiling), so your custom shortcut never fires. Combos that are reliably free: `Meta+Alt+<arrow>`, `Meta+Shift+<letter>`, `Meta+<F-key>`. If a shortcut you've defined doesn't fire, delete it and re-add it from scratch — Plasma's shortcut daemon occasionally gets stuck mid-registration.

## License

[MIT](LICENSE). Use it, fork it, ship it.
