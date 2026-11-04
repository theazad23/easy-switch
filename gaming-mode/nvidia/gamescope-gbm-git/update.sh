#!/usr/bin/env bash
# Build + install gamescope-gbm-git from latest upstream master with the GBM patch.
# Run from anywhere; asks for sudo (pacman) at the install step.
#   ./update.sh            build and install
#   ./update.sh --check    only show how far upstream moved since the installed build
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$here"
if [[ "${1:-}" == --check ]]; then
    inst=$(pacman -Q gamescope-gbm-git 2>/dev/null | awk '{print $2}' | sed -E 's/.*\.g([0-9a-f]+)-.*/\1/') || true
    head=$(git ls-remote https://github.com/ValveSoftware/gamescope.git refs/heads/master | cut -c1-7)
    echo "installed: ${inst:-not installed}   upstream master: $head"
    exit 0
fi
# Build only (-s: install makedepends, -f: rebuild even if this version exists).
makepkg -sf --noconfirm --needed || {
    echo
    echo "Build failed. If it says the patch no longer applies: ./refresh-patch.sh, then re-run ./update.sh"
    exit 1
}
# Install interactively: pacman asks to replace gamescope / gamescope-git the first time,
# and --noconfirm would answer that with its default "N".
pkg=$(makepkg --packagelist | head -1)
sudo pacman -U "$pkg"
echo
echo "Installed: $(pacman -Q gamescope-gbm-git)"
echo "Next Gaming Mode start uses it (50-nvidia-tv-fix.lua turns drm_gbm_scanout on)."
