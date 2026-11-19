#!/usr/bin/env bash
# Record what `doctor` sees on a PC into tests/fixtures/<host>.json (read-only on
# the PC; home directory and user name are replaced in the recording).
#   tests/capture.sh bonestorm lisa
# Runs this checkout's code on the PC from a temp copy, so an unpushed branch works.
set -euo pipefail
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
for host in "$@"; do
    out="$repo/tests/fixtures/$host.json"
    tar -C "$repo" -cf - easy-switch easyswitch gaming-mode \
        | ssh -o ConnectTimeout=8 "$host" 'bash -c "d=\$(mktemp -d) && tar -C \$d -xf - && python3 \$d/easy-switch doctor --record; rc=\$?; rm -rf \$d; exit \$rc"' \
        > "$out.tmp"
    python3 -c 'import json,sys; json.load(open(sys.argv[1]))' "$out.tmp"
    mv "$out.tmp" "$out"
    echo "recorded $out"
done
