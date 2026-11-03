#!/usr/bin/env bash
# User half of the Gaming Mode setup (no root). Idempotent; re-run after editing
# the templates. See GAMING-MODE.md for the full order of steps.
#   ./install.sh            # AMD / Intel
#   ./install.sh --nvidia   # also install the NVIDIA-only gamescope workarounds
set -euo pipefail
GM="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(dirname "$GM")"
NVIDIA=0; [[ "${1:-}" == "--nvidia" ]] && NVIDIA=1

say()  { printf '  %s\n' "$*"; }
warn() { printf '  ! %s\n' "$*" >&2; }
put()  {  # put <template> <dest> [mode]: copy with @HOME@ filled in; back up a differing existing file once
    local src="$1" dst="$2" mode="${3:-644}" tmp
    mkdir -p "$(dirname "$dst")"
    tmp="$(mktemp)"; sed "s|@HOME@|$HOME|g" "$src" > "$tmp"
    if [[ -e "$dst" ]] && ! cmp -s "$tmp" "$dst"; then
        [[ -e "$dst.pre-gaming-mode" ]] || cp -a "$dst" "$dst.pre-gaming-mode"
    fi
    install -m "$mode" "$tmp" "$dst"; rm -f "$tmp"; say "installed $dst"
}

echo "== checks"
pacman -Q gamescope-session-cachyos >/dev/null 2>&1 || warn "gamescope-session-cachyos not installed: sudo pacman -S gamescope-session-cachyos"
python3 -c 'import evdev' 2>/dev/null || warn "python-evdev missing (needed for Gaming Mode hotkeys): sudo pacman -S python-evdev"
id -nG | grep -qw input || warn "user not in 'input' group (needed for Gaming Mode hotkeys): sudo usermod -aG input $USER, then log out/in"
command -v powerprofilesctl >/dev/null || warn "powerprofilesctl missing (steam-game-performance needs power-profiles-daemon)"
[[ -x "$HOME/.local/bin/easy-switch" ]] || { say "linking easy-switch"; "$REPO/install.sh" >/dev/null; }

echo "== scripts -> ~/.local/bin"
for f in "$GM"/bin/*; do put "$f" "$HOME/.local/bin/$(basename "$f")" 755; done

echo "== systemd user units"
for f in "$GM"/systemd/user/*.service; do put "$f" "$HOME/.config/systemd/user/$(basename "$f")"; done
put "$GM/systemd/user/gamescope-session.service.d/easy-switch.conf" \
    "$HOME/.config/systemd/user/gamescope-session.service.d/easy-switch.conf"

echo "== launchers"
put "$GM/applications/gaming-mode.desktop" "$HOME/Desktop/gaming-mode.desktop" 755
for f in "$GM"/applications/*.desktop; do put "$f" "$HOME/.local/share/applications/$(basename "$f")"; done
put "$GM/autostart/easy-switch-restore.desktop" "$HOME/.config/autostart/easy-switch-restore.desktop"
# Desktop Steam must run as the Deck client too (-steamdeck), or it and Gaming
# Mode fight over the client channel and re-download ~400 MB on every switch.
if [[ -f /usr/share/applications/steam.desktop ]]; then
    { sed -E 's#^(Exec=/usr/bin/steam)( |$)#\1 -steamdeck\2#' /usr/share/applications/steam.desktop \
        | sed '1a # Local copy: adds -steamdeck so desktop Steam uses the same client/channel as Gaming Mode'; } \
        > "$HOME/.local/share/applications/steam.desktop"
    say "installed ~/.local/share/applications/steam.desktop (-steamdeck)"
fi

echo "== MangoHud profiles (only if missing)"
for f in "$GM"/mangohud/*.conf; do
    d="$HOME/.config/MangoHud/$(basename "$f")"; [[ -e "$d" ]] && say "kept $d" || put "$f" "$d"
done

echo "== Steam safety switches"
mkdir -p "$HOME/.config"; touch "$HOME/.config/inhibit-short-session-tracker"
say "disabled Gaming Mode's Steam auto-reset (~/.config/inhibit-short-session-tracker)"
beta="$HOME/.local/share/Steam/package/beta"
if [[ -f "$beta" ]] && grep -qx 'publicbeta' "$beta"; then
    printf 'steamdeck_publicbeta' > "$beta"; say "Steam beta channel -> steamdeck_publicbeta (shared by desktop + Gaming Mode)"
fi

if (( NVIDIA )); then
    echo "== NVIDIA workarounds"
    put "$GM/nvidia/gamescope-wrapper" "$HOME/.local/share/gaming-mode/bin/gamescope" 755
    put "$GM/nvidia/gamescope-session-nvidia.conf" "$HOME/.config/systemd/user/gamescope-session.service.d/nvidia.conf"
    put "$GM/nvidia/50-nvidia-tv-fix.lua" "$HOME/.config/gamescope/scripts/50-nvidia-tv-fix.lua"
fi

echo "== enable"
systemctl --user daemon-reload
# CachyOS default: every Plasma login re-arms autologin into Gaming Mode. We want
# "last mode wins" instead (handled by gaming-mode-stopped + the session drop-in).
systemctl --user mask cachyos-gamescope-autologin.service >/dev/null 2>&1 || true
systemctl --user enable steam.service steam-game-performance.service \
    easy-switch-hotkeys.service gaming-mode-diag.service >/dev/null
systemctl --user restart steam-game-performance.service
say "enabled steam, steam-game-performance, easy-switch-hotkeys, gaming-mode-diag; masked cachyos-gamescope-autologin"

cat <<EOF

== next (see GAMING-MODE.md):
  1. sudo sh $GM/root/login-manager-setup.sh
  2. add gamescope_output / hotkey / mangohud / restart_hotkey to ~/.config/easy-switch/config.toml
  3. easy-switch <mode> on the desktop, then double-click "Return to Gaming Mode"
EOF
