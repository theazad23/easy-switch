#!/usr/bin/env bash
# Kept for old habits and docs: the installer is `easy-switch install` now
# (easyswitch/install.py; same steps, symlinks instead of copies, --dry-run).
set -euo pipefail
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
[[ -x "$HOME/.local/bin/easy-switch" ]] || "$repo/install.sh" >/dev/null
exec "$repo/easy-switch" install "$@"
