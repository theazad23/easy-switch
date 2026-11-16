#!/bin/bash
# Prism pre-launch command for the "Main" instance (bonestorm).
#
# Under gamescope (Steam Gaming Mode), Minecraft 26.3 in exclusive fullscreen
# stalls its SDL window every frame ("Failed to synchronize SDL window", ~10 fps),
# so there it runs WINDOWED at exactly the gamescope output size.
# On the desktop (Plasma) it runs fullscreen.
#
# Window size in Gaming Mode, in order of preference:
#   1. preferred mode of the single enabled DRM connector (the panel gamescope drives)
#   2. gamescope's "selecting mode" journal line
#   3. 2560x1440
set -u

opts="${INST_MC_DIR:?INST_MC_DIR not set - run this as a Prism pre-launch command}/options.txt"
log() { echo "fullscreen-by-session: $*" >&2; }

# set_opt KEY VALUE: replace "KEY:..." in options.txt, or append it
set_opt() {
    touch "$opts"
    if grep -q "^$1:" "$opts"; then
        sed -i "s|^$1:.*|$1:$2|" "$opts"
    else
        printf '%s:%s\n' "$1" "$2" >> "$opts"
    fi
}

if [ -n "${GAMESCOPE_WAYLAND_DISPLAY:-}" ] || [ "${XDG_CURRENT_DESKTOP:-}" = gamescope ]; then
    size=""
    # 1. the connector gamescope is driving: in Gaming Mode it is the only enabled
    #    one, and gamescope uses its preferred mode (first line of "modes").
    #    (Not the Xwayland root size: on bonestorm that reports 3840x2160 even
    #    when gamescope drives the 2560x1440 desk panel.)
    enabled=( $(grep -l '^enabled$' /sys/class/drm/card*-*/enabled 2>/dev/null) )
    if [ ${#enabled[@]} -eq 1 ]; then
        size=$(head -1 "${enabled[0]%/enabled}/modes" 2>/dev/null)
    fi
    # 2. gamescope's own log line "drm: selecting mode WxH@R" (this boot)
    if ! [[ $size =~ ^[0-9]+x[0-9]+$ ]]; then
        size=$(journalctl --user -b -o cat 2>/dev/null | grep -a 'selecting mode' | tail -1 |
               grep -oE '[0-9]+x[0-9]+' | head -1)
    fi
    # 3. fallback
    [[ $size =~ ^[0-9]+x[0-9]+$ ]] || size=2560x1440
    w=${size%x*}; h=${size#*x}
    set_opt fullscreen false
    set_opt overrideWidth "$w"
    set_opt overrideHeight "$h"
    log "gamescope session: windowed ${w}x${h}"
else
    set_opt fullscreen true
    set_opt overrideWidth 0     # 0 = no override (normal window size if un-fullscreened)
    set_opt overrideHeight 0
    log "desktop session: fullscreen"
fi
exit 0
