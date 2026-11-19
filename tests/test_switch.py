"""The mode switcher's pure parts: kscreen-doctor parsing, the enable / disable
command batches, sink -> card profile, hotkeys and the config file editing."""

import tomllib
import unittest
from unittest import mock

from easyswitch import switch

KSCREEN = """\
Output: 1 DP-3 enabled connected priority 1 DisplayPort Modes: 0:2560x1440@60 1:2560x1440@165*! 2:1920x1080@60 Geometry: 0,0 2560x1440 Scale: 1 Rotation: 1 Overscan: 0 Vrr: Automatic
Output: 2 HDMI-A-1 disabled connected priority 0 HDMI Modes: 0:3840x2160@60*! 1:1920x1080@60 Geometry: 2560,0 3840x2160 Scale: 1 Rotation: 1
Output: 3 DP-2 disabled disconnected priority 0 DisplayPort Modes: Geometry: 0,0 0x0 Scale: 1 Rotation: 8
"""
# kscreen-doctor prints one attribute per line; the parser reads line by line
KSCREEN_LINES = "\n".join(
    part
    for line in KSCREEN.splitlines()
    for part in __import__("re").sub(
        r" (enabled|disabled|connected|disconnected|priority \d+|Modes:|Geometry:|Rotation:)", r"\n\t\1", line
    ).split("\n")
)


def fake_run(stdout):
    return mock.Mock(stdout=stdout, returncode=0)


class Parse(unittest.TestCase):
    def outputs(self):
        with mock.patch.object(switch, "run", return_value=fake_run(KSCREEN_LINES)):
            return switch.parse_outputs()

    def test_outputs(self):
        o = self.outputs()
        self.assertEqual(set(o), {"DP-3", "HDMI-A-1", "DP-2"})
        self.assertTrue(o["DP-3"]["enabled"] and o["DP-3"]["connected"] and o["DP-3"]["primary"])
        self.assertEqual(o["DP-3"]["mode"], "2560x1440@165")
        self.assertTrue(o["HDMI-A-1"]["connected"] and not o["HDMI-A-1"]["enabled"])
        self.assertEqual(o["HDMI-A-1"]["position"], "2560,0")

    def test_disconnected_is_not_connected(self):
        self.assertFalse(self.outputs()["DP-2"]["connected"])

    def test_rotation(self):
        self.assertEqual(self.outputs()["DP-2"]["rotation"], "right")


class Audio(unittest.TestCase):
    def test_profile_from_sink(self):
        self.assertEqual(
            switch.sink_card_profile("alsa_output.pci-0000_08_00.1.hdmi-stereo-extra1"),
            ("alsa_card.pci-0000_08_00.1", "output:hdmi-stereo-extra1"),
        )

    def test_pro_audio(self):
        card, prof = switch.sink_card_profile("alsa_output.usb-X-00.pro-output-0")
        self.assertEqual((card, prof), ("alsa_card.usb-X-00", "pro-audio"))

    def test_not_alsa(self):
        self.assertIsNone(switch.sink_card_profile("easyeffects_sink"))


class Hotkeys(unittest.TestCase):
    def test_parse(self):
        mods, key = switch.parse_hotkey("ctrl+alt+down")
        self.assertEqual(mods, frozenset({"ctrl", "alt"}))
        self.assertIn("DOWN", key.upper())


MODE = {
    "description": "TV + TV audio",
    "requires_any": ["HDMI-A-1"],
    "strict": True,
    "audio": "alsa_output.pci-0000_08_00.1.hdmi-stereo-extra1",
    "outputs": {
        "HDMI-A-1": {"enable": True, "primary": True, "mode": "3840x2160@60"},
        "DP-1": {"enable": False},
    },
}


class ConfigEditing(unittest.TestCase):
    def test_block_round_trip(self):
        text = switch.emit_mode_block("tv", MODE)
        self.assertEqual(tomllib.loads(text)["modes"]["tv"], MODE)

    def test_replace_keeps_siblings(self):
        both = "# my PC\n\n" + switch.emit_mode_block("desk", MODE) + "\n" + switch.emit_mode_block("tv", MODE)
        changed = dict(MODE, description="new")
        out = switch.replace_mode_block(both, "tv", switch.emit_mode_block("tv", changed))
        cfg = tomllib.loads(out)
        self.assertEqual(cfg["modes"]["tv"]["description"], "new")
        self.assertEqual(cfg["modes"]["desk"], MODE)
        self.assertTrue(out.startswith("# my PC"))

    def test_delete_keeps_siblings(self):
        both = switch.emit_mode_block("desk", MODE) + "\n" + switch.emit_mode_block("tv", MODE)
        cfg = tomllib.loads(switch.delete_mode_block(both, "desk"))
        self.assertEqual(set(cfg["modes"]), {"tv"})


class ActiveMode(unittest.TestCase):
    CFG = {
        "modes": {
            "desk": {"outputs": {"DP-1": {"enable": True, "primary": True}, "HDMI-A-1": {"enable": False}}},
            "tv": {"outputs": {"HDMI-A-1": {"enable": True, "primary": True}, "DP-1": {"enable": False}}},
        }
    }

    def detect(self, enabled):
        with mock.patch.object(switch, "drm_attr", side_effect=lambda n, a: "enabled" if n in enabled else "disabled"):
            return switch.detect_active_mode(self.CFG)

    def test_matches_the_screen_that_is_on(self):
        self.assertEqual(self.detect({"HDMI-A-1"}), "tv")
        self.assertEqual(self.detect({"DP-1"}), "desk")

    def test_both_on_matches_nothing(self):
        self.assertIsNone(self.detect({"DP-1", "HDMI-A-1"}))


if __name__ == "__main__":
    unittest.main()
