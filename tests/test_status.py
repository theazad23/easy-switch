"""status / commands JSON on the recordings of both PCs."""

import copy
import json
import unittest
from pathlib import Path

from easyswitch import status
from easyswitch.system import Replay

FIX = Path(__file__).parent / "fixtures"
RAW = {h: json.loads((FIX / f"{h}.json").read_text()) for h in ("bonestorm", "lisa")}


def screens(d, **on):
    d = copy.deepcopy(d)
    for k in d["read"]:
        if k.startswith("/sys/class/drm/") and k.endswith("/enabled"):
            conn = k.split("/")[4].split("-", 1)[1]
            d["read"][k] = ("enabled" if on.get(conn.replace("-", "_")) else "disabled") + "\n"
    return d


class Status(unittest.TestCase):
    def test_shape(self):
        for host, d in RAW.items():
            s = status.status(Replay(d))
            self.assertEqual(s["host"], host)
            self.assertIn(s["session"], ("desktop", "gaming"))
            self.assertIsInstance(s["game_running"], bool)
            json.dumps(s)

    def test_modes_listed(self):
        self.assertEqual(set(status.status(Replay(RAW["lisa"]))["modes"]), {"desk", "tv"})
        self.assertEqual(set(status.status(Replay(RAW["bonestorm"]))["modes"]), {"desk", "couch"})

    def test_mode_follows_the_screen_that_is_on(self):
        s = status.status(Replay(screens(RAW["lisa"], HDMI_A_1=True)))
        self.assertEqual((s["mode"], s["screens_on"]), ("tv", ["HDMI-A-1"]))
        s = status.status(Replay(screens(RAW["lisa"], DP_1=True)))
        self.assertEqual(s["mode"], "desk")

    def test_no_mode_when_screens_are_off_or_both_on(self):
        self.assertIsNone(status.status(Replay(screens(RAW["lisa"])))["mode"])
        self.assertIsNone(status.status(Replay(screens(RAW["lisa"], DP_1=True, HDMI_A_1=True)))["mode"])

    def test_gaming_session(self):
        d = copy.deepcopy(RAW["bonestorm"])
        key = next(k for k in d["exists"] if k.endswith("/gamescope-environment"))
        d["exists"][key] = True
        self.assertEqual(status.status(Replay(d))["session"], "gaming")

    def test_vendor(self):
        self.assertEqual(status.status(Replay(RAW["bonestorm"]))["gpu"], ["nvidia"])
        self.assertEqual(status.status(Replay(RAW["lisa"]))["gpu"], ["amd"])


class Commands(unittest.TestCase):
    def test_switch_offers_this_pcs_modes(self):
        c = {x["id"]: x for x in status.commands(Replay(RAW["bonestorm"]))}
        self.assertEqual(c["switch"]["options"], ["desk", "couch"])
        self.assertEqual(c["switch"]["state"], "mode")
        self.assertIn("restart_gaming_mode", c)


if __name__ == "__main__":
    unittest.main()
