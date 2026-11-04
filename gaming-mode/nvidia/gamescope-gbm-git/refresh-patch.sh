#!/usr/bin/env bash
# Re-base the GBM patch onto the latest upstream gamescope master and re-export it.
# Uses the working clone in ~/src/gamescope-gbm (branch gbm-on-master). Only git, no build.
#   ./refresh-patch.sh
# If git stops with a conflict: fix the files it lists, `git add` them, then
#   git -C ~/src/gamescope-gbm rebase --continue
# and run this script again to export the patch.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo="${GAMESCOPE_GBM_REPO:-$HOME/src/gamescope-gbm}"
cd "$repo"
if [ -d .git/rebase-merge ] || [ -d .git/rebase-apply ]; then
    echo "A rebase is in progress in $repo -- finish it (git rebase --continue) first." >&2; exit 1
fi
git remote get-url upstream >/dev/null 2>&1 || git remote add upstream https://github.com/ValveSoftware/gamescope.git
git fetch -q upstream master
git checkout -q gbm-on-master
old=$(git merge-base HEAD upstream/master | cut -c1-7)
new=$(git rev-parse --short upstream/master)
if [ "$old" != "$new" ]; then
    echo "Rebasing GBM commits from upstream $old onto $new ..."
    git -c user.name=local -c user.email=local@localhost rebase upstream/master
fi
git diff --no-ext-diff upstream/master gbm-on-master -- . ':(exclude).gitignore' > "$here/0001-nvidia-gbm-scanout.patch"
echo "Patch re-exported against upstream $new: $(grep -c '^diff --git' "$here/0001-nvidia-gbm-scanout.patch") files."
echo "Now: ./update.sh"
