"""Command dispatch. Subcommands live in their own modules; everything else is
the mode switcher (`easy-switch <mode>`, `add`, `remove`, `--list` ...)."""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "doctor":
        from . import doctor

        return doctor.main(argv[1:])
    from . import switch

    return switch.main(argv)
