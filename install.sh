#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="${BIN_DIR:-$HOME/.local/bin}"
CFG_DIR="${CFG_DIR:-$HOME/.config/easy-switch}"

mkdir -p "$BIN_DIR" "$CFG_DIR"

ln -sfn "$REPO_DIR/easy-switch" "$BIN_DIR/easy-switch"
echo "Linked: $BIN_DIR/easy-switch -> $REPO_DIR/easy-switch"

if [[ -f "$CFG_DIR/config.toml" ]]; then
    echo "Config already present: $CFG_DIR/config.toml (left untouched)"
else
    echo
    echo "No config yet. Starter configs in $REPO_DIR/examples:"
    for f in "$REPO_DIR"/examples/*.toml; do
        [[ -e "$f" ]] || continue
        echo "  - $(basename "$f")"
    done
    echo
    echo "Copy one and edit it for this host, e.g.:"
    echo "  cp $REPO_DIR/examples/basement.toml $CFG_DIR/config.toml"
fi

case ":$PATH:" in
    *":$BIN_DIR:"*) ;;
    *) echo; echo "Note: $BIN_DIR is not on your PATH. Add it to your shell rc to use 'easy-switch' directly." ;;
esac
