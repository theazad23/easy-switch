"""The one door to the machine for read-only checks: files, links, directories
and commands. `doctor` only talks to a System, so a recording of a real PC can
stand in for it in the tests (tests/fixtures/<host>.json)."""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path


class System:
    def __init__(self) -> None:
        self.home = str(Path.home())

    def path(self, p: str) -> str:
        return self.home + p[1:] if p.startswith("~") else p

    def read(self, p: str) -> str | None:
        try:
            return Path(self.path(p)).read_text(errors="replace")
        except OSError:
            return None

    def exists(self, p: str) -> bool:
        return os.path.lexists(self.path(p))

    def readlink(self, p: str) -> str | None:
        try:
            return os.readlink(self.path(p))
        except OSError:
            return None

    def realpath(self, p: str) -> str:
        return os.path.realpath(self.path(p))

    def listdir(self, p: str) -> list[str] | None:
        try:
            return sorted(os.listdir(self.path(p)))
        except OSError:
            return None

    def cmd(self, *args: str) -> tuple[int, str]:
        """(exit code, stdout+stderr). 127 when the program is not installed."""
        try:
            r = subprocess.run(
                list(args),
                capture_output=True,
                text=True,
                timeout=10,
                stdin=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            return 127, ""
        except subprocess.TimeoutExpired:
            return 124, ""
        return r.returncode, r.stdout + r.stderr


KINDS = ("read", "exists", "readlink", "realpath", "listdir", "cmd")


class Recorder(System):
    """A System that remembers every answer it gave, with the home directory and
    user name replaced, so the recording can be committed."""

    FAKE_HOME = "/home/user"

    def __init__(self) -> None:
        super().__init__()
        self.user = Path(self.home).name
        self.log: dict[str, dict] = {k: {} for k in KINDS}

    def _scrub(self, v):
        if isinstance(v, str):
            return v.replace(self.home, self.FAKE_HOME).replace(self.user, "user")
        if isinstance(v, list):
            return [self._scrub(x) for x in v]
        return v

    def read(self, p):
        v = super().read(p)
        kept = self._scrub(v)
        if kept and p.startswith(("/etc/", "/proc/mounts")):
            # system files name the house network and disks: keep the shape only
            kept = re.sub(r"\b(?:10|192\.168|172\.(?:1[6-9]|2\d|3[01]))(?:\.\d{1,3}){2,3}\b", "192.0.2.1", kept)
            kept = re.sub(r"[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}", "00000000-0000-0000-0000-000000000000", kept)
            kept = re.sub(r"UUID=[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}", "UUID=0000-0000", kept)
        self.log["read"][self._scrub(p)] = kept
        return v

    def exists(self, p):
        v = super().exists(p)
        self.log["exists"][self._scrub(p)] = v
        return v

    def readlink(self, p):
        v = super().readlink(p)
        self.log["readlink"][self._scrub(p)] = self._scrub(v)
        return v

    def realpath(self, p):
        v = super().realpath(p)
        self.log["realpath"][self._scrub(p)] = self._scrub(v)
        return v

    def listdir(self, p):
        v = super().listdir(p)
        self.log["listdir"][self._scrub(p)] = self._scrub(v)
        return v

    def cmd(self, *args):
        rc, out = super().cmd(*args)
        self.log["cmd"][self._scrub(" ".join(args))] = [rc, self._scrub(out)]
        return rc, out

    def dump(self) -> str:
        return json.dumps({"home": self.FAKE_HOME, **self.log}, indent=1, sort_keys=True)


class Replay(System):
    """Answers from a recording. Asking for something that was never recorded is
    an error, so a new check can't quietly pass on a stale recording: record
    again (tests/capture.sh <host>) or add the answer in the test."""

    def __init__(self, data: dict) -> None:
        self.data = data
        self.home = data["home"]

    def _get(self, kind: str, key: str):
        try:
            return self.data[kind][key]
        except KeyError:
            raise KeyError(f"recording has no {kind} for {key!r}") from None

    def read(self, p):
        return self._get("read", p)

    def exists(self, p):
        return self._get("exists", p)

    def readlink(self, p):
        return self._get("readlink", p)

    def realpath(self, p):
        return self._get("realpath", p)

    def listdir(self, p):
        return self._get("listdir", p)

    def cmd(self, *args):
        return tuple(self._get("cmd", " ".join(args)))
