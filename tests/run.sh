#!/usr/bin/env bash
# All tests. No screen, no Steam and no PC needed: they run on recordings.
cd "$(dirname "${BASH_SOURCE[0]}")/.." && exec python3 -m unittest discover -s tests -t . "$@"
