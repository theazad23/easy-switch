"""doctor against recordings of the two real PCs: bonestorm (NVIDIA, Plasma
Login) and lisa (AMD, SDDM). Each test changes one thing in a recording and
checks that doctor says so. Run: tests/run.sh"""

import copy
import json
import unittest
from pathlib import Path

from easyswitch import gpu, manifest
from easyswitch.doctor import FAIL, OK, SKIP, WARN, Doctor
from easyswitch.system import Replay

FIX = Path(__file__).parent / "fixtures"
RAW = {h: json.loads((FIX / f"{h}.json").read_text()) for h in ("bonestorm", "lisa")}
HOME = "/home/user"


def healthy(host: str) -> dict:
    """The recording with every installed file made equal to the repo, so tests
    start from a PC with nothing wrong in 'Installed files'."""
    d = copy.deepcopy(RAW[host])
    nvidia = host == "bonestorm"
    for it in manifest.items():
        if it.when == "always" or nvidia:
            d["read"][it.dest] = manifest.rendered(it, HOME)
    if host == "lisa":
        d["listdir"]["~/.config/environment.d"] = ["gaming.conf"]
    return d


def run(data: dict):
    res = Doctor(Replay(data)).run()
    return {(r.group, r.name): r for r in res}, res


def status(res, name):
    return next(r for r in res if r.name == name).status


class Gpu(unittest.TestCase):
    def test_vendor_per_pc(self):
        b = gpu.detect(Replay(RAW["bonestorm"]))
        l = gpu.detect(Replay(RAW["lisa"]))
        self.assertEqual([g.vendor for g in b], ["nvidia"])
        self.assertEqual([g.vendor for g in l], ["amd"])
        self.assertIn("HDMI-A-1", b[0].connectors)
        self.assertEqual(gpu.for_connector(l, "DP-1").driver, "amdgpu")

    def test_writeback_is_not_a_screen(self):
        l = gpu.detect(Replay(RAW["lisa"]))
        self.assertFalse(any(c.startswith("Writeback") for c in l[0].connectors))

    def test_nvidia_version(self):
        self.assertRegex(gpu.nvidia_version(Replay(RAW["bonestorm"])), r"^\d{3}\.\d+")
        d = healthy("lisa")  # doctor never asks an AMD PC for this, so it isn't recorded
        d["read"]["/proc/driver/nvidia/version"] = None
        self.assertIsNone(gpu.nvidia_version(Replay(d)))

    def test_two_cards(self):
        d = healthy("lisa")
        d["listdir"]["/sys/class/drm"] += ["card2", "card2-eDP-1"]
        d["realpath"]["/sys/class/drm/card2/device/driver"] = "/sys/bus/pci/drivers/nvidia"
        gs = gpu.detect(Replay(d))
        self.assertEqual({g.vendor for g in gs}, {"amd", "nvidia"})
        self.assertEqual(gpu.for_connector(gs, "eDP-1").vendor, "nvidia")


class Healthy(unittest.TestCase):
    def test_no_failures_on_either_pc(self):
        for host in RAW:
            _, res = run(healthy(host))
            self.assertEqual([(r.name, r.detail) for r in res if r.status == FAIL], [], host)

    def test_nvidia_extras_only_expected_on_nvidia(self):
        # lisa has none of the NVIDIA files and that is correct
        _, res = run(healthy("lisa"))
        self.assertEqual(status(res, "files"), OK)
        self.assertFalse(any(r.name == "NVIDIA gamescope build" for r in res))
        _, res = run(healthy("bonestorm"))
        self.assertEqual(status(res, "NVIDIA gamescope build"), OK)


class Files(unittest.TestCase):
    def test_missing_file(self):
        d = healthy("lisa")
        d["read"]["~/.local/bin/gaming-mode-stopped"] = None
        _, res = run(d)
        r = next(r for r in res if r.name == "missing")
        self.assertEqual(r.status, FAIL)
        self.assertIn("gaming-mode-stopped", r.detail)

    def test_drifted_file(self):
        d = healthy("bonestorm")
        d["read"]["~/.local/bin/gaming-mode-diag"] += "# local edit\n"
        _, res = run(d)
        self.assertIn("gaming-mode-diag", next(r for r in res if r.name == "differs from the repo").detail)

    def test_nvidia_leftovers_on_amd(self):
        d = healthy("lisa")
        d["read"]["~/.local/share/gaming-mode/bin/gamescope"] = "#!/bin/sh\n"
        _, res = run(d)
        r = next(r for r in res if r.name == "NVIDIA-only leftovers")
        self.assertEqual(r.status, FAIL)

    def test_stock_gamescope_on_nvidia_warns(self):
        d = healthy("bonestorm")
        d["cmd"]["pacman -Q gamescope-gbm-git"] = [1, "error: package 'gamescope-gbm-git' was not found\n"]
        _, res = run(d)
        self.assertEqual(status(res, "NVIDIA gamescope build"), WARN)


class Modes(unittest.TestCase):
    def cfg(self, host, old, new):
        d = healthy(host)
        key = "~/.config/easy-switch/config.toml"
        self.assertIn(old, d["read"][key])
        d["read"][key] = d["read"][key].replace(old, new)
        return d

    def test_unknown_connector(self):
        _, res = run(self.cfg("lisa", 'gamescope_output = "DP-1"', 'gamescope_output = "DP-9"'))
        r = next(r for r in res if r.name == "mode desk")
        self.assertEqual(r.status, FAIL)
        self.assertIn("DP-9", r.detail)

    def test_missing_mangohud_profile(self):
        d = healthy("lisa")
        d["exists"]["~/.config/MangoHud/tv.conf"] = False
        _, res = run(d)
        self.assertEqual(status(res, "mode tv"), FAIL)

    def test_duplicate_hotkey(self):
        _, res = run(self.cfg("lisa", 'hotkey = "ctrl+alt+right"', 'hotkey = "ctrl+alt+left"'))
        self.assertIn("also used", next(r for r in res if r.name == "mode tv").detail)

    def test_hdmi_sink_made_on_switch_is_fine(self):
        # the TV's sound output only exists after its card profile is switched
        _, res = run(healthy("lisa"))
        self.assertEqual(status(res, "mode tv"), OK)

    def test_sound_device_gone_is_a_warning(self):
        d = healthy("lisa")
        d["cmd"]["pactl list sinks short"] = [0, ""]
        d["cmd"]["pactl list cards short"] = [0, ""]
        _, res = run(d)
        self.assertEqual(status(res, "mode desk"), WARN)

    def test_mangohud_regular_file(self):
        d = healthy("lisa")
        d["readlink"]["~/.config/MangoHud/MangoHud.conf"] = None
        d["exists"]["~/.config/MangoHud/MangoHud.conf"] = True
        _, res = run(d)
        self.assertEqual(status(res, "MangoHud.conf"), FAIL)

    def test_broken_config(self):
        d = healthy("lisa")
        d["read"]["~/.config/easy-switch/config.toml"] = "[modes.desk\n"
        _, res = run(d)
        self.assertEqual(status(res, "config"), FAIL)


class Environment(unittest.TestCase):
    def env(self, host, extra):
        d = healthy(host)
        d["read"]["~/.config/environment.d/gaming.conf"] += extra
        return run(d)[1]

    def test_native_wayland_fails(self):
        self.assertEqual(status(self.env("lisa", "\nPROTON_ENABLE_WAYLAND=1\n"), "gaming.conf"), FAIL)

    def test_nvidia_settings_on_amd(self):
        res = self.env("lisa", "\nPROTON_DLSS_UPGRADE=1\n")
        r = next(r for r in res if r.name == "gaming.conf")
        self.assertEqual(r.status, WARN)
        self.assertIn("PROTON_DLSS_UPGRADE", r.detail)

    def test_amd_settings_on_nvidia(self):
        self.assertEqual(status(self.env("bonestorm", "\nPROTON_FSR4_UPGRADE=1\n"), "gaming.conf"), WARN)

    def test_non_environment_file(self):
        # as found on lisa 2026-11-19: a portal config dropped into environment.d
        _, res = run(RAW["lisa"])
        self.assertEqual(status(res, "portals.conf"), FAIL)


class FreshInstall(unittest.TestCase):
    FSTAB = "/etc/fstab"

    def test_games_drive_without_nofail(self):
        d = healthy("bonestorm")
        self.assertIn("nofail", d["read"][self.FSTAB])
        d["read"][self.FSTAB] = d["read"][self.FSTAB].replace("nofail", "noatime")
        _, res = run(d)
        self.assertEqual(status(res, "drive /mnt/fast-storage"), FAIL)

    def test_drive_in_fstab_but_not_mounted(self):
        d = healthy("bonestorm")
        d["read"]["/proc/mounts"] = "\n".join(
            ln for ln in d["read"]["/proc/mounts"].splitlines() if " /mnt/fast-storage " not in ln
        )
        _, res = run(d)
        self.assertEqual(status(res, "drive /mnt/fast-storage"), WARN)

    def test_automounted_share_is_fine_unmounted(self):
        d = healthy("lisa")
        self.assertIn("x-systemd.automount", d["read"][self.FSTAB])
        d["read"]["/proc/mounts"] = ""
        _, res = run(d)
        self.assertEqual(status(res, "drive /mnt/games"), OK)

    def test_steam_prompt_not_authorized(self):
        d = healthy("lisa")
        d["read"]["~/.local/share/flatpak/db/kde-authorized"] = None
        _, res = run(d)
        self.assertEqual(status(res, "Steam remote-control prompt"), WARN)

    def test_inline_comment_becomes_the_value(self):
        d = healthy("lisa")
        d["read"]["~/.config/environment.d/gaming.conf"] += "\nFOO=1   # note\n"
        _, res = run(d)
        r = next(r for r in res if r.name == "gaming.conf")
        self.assertEqual(r.status, FAIL)
        self.assertIn("FOO", r.detail)

    def test_indented_variable_is_skipped_by_systemd(self):
        d = healthy("lisa")
        d["read"]["~/.config/environment.d/gaming.conf"] += "\n  BAR=1\n"
        _, res = run(d)
        self.assertIn("BAR", next(r for r in res if r.name == "gaming.conf").detail)

    def test_recording_hides_the_house_network_and_disks(self):
        for host, d in RAW.items():
            sysfiles = d["read"][self.FSTAB] + d["read"]["/proc/mounts"]
            self.assertNotRegex(sysfiles, r"192\.168\.", host)
            self.assertNotRegex(sysfiles, r"UUID=(?!0000)[0-9a-f]{4}", host)


class OldCopies(unittest.TestCase):
    def test_unit_with_home_written_in_is_not_drift(self):
        d = healthy("lisa")
        unit = "~/.config/systemd/user/gaming-mode-diag.service"
        d["read"][unit] = d["read"][unit].replace("%h", HOME)
        self.assertIn(HOME, d["read"][unit])
        _, res = run(d)
        self.assertEqual(status(res, "files"), OK)


class GamingMode(unittest.TestCase):
    def test_plasma_login_needs_session_sync(self):
        d = healthy("bonestorm")
        d["cmd"]["systemctl is-enabled plasmalogin-session-sync.path"] = [1, "disabled\n"]
        _, res = run(d)
        self.assertEqual(status(res, "session sync"), FAIL)

    def test_sddm_has_no_session_sync_check(self):
        _, res = run(healthy("lisa"))
        self.assertFalse(any(r.name == "session sync" for r in res))

    def test_autologin_rearm_must_be_masked(self):
        d = healthy("lisa")
        d["cmd"]["systemctl --user is-enabled cachyos-gamescope-autologin.service"] = [0, "enabled\n"]
        _, res = run(d)
        self.assertEqual(status(res, "CachyOS autologin re-arm"), FAIL)

    def test_beta_channel_tug_of_war(self):
        d = healthy("lisa")
        d["read"]["~/.local/share/Steam/package/beta"] = "publicbeta"
        _, res = run(d)
        self.assertEqual(status(res, "client channel"), FAIL)

    def test_second_steam_autostart(self):
        d = healthy("lisa")
        d["listdir"]["~/.config/autostart"] = d["listdir"]["~/.config/autostart"] + ["steam.desktop"]
        _, res = run(d)
        self.assertEqual(status(res, "Plasma autostart"), FAIL)

    def test_not_in_input_group(self):
        d = healthy("lisa")
        d["cmd"]["id -nG"] = [0, "user wheel audio\n"]
        _, res = run(d)
        self.assertEqual(status(res, "input group"), FAIL)

    def test_pc_without_gaming_mode_skips_it(self):
        d = healthy("lisa")
        key = "~/.config/easy-switch/config.toml"
        d["read"][key] = "\n".join(ln for ln in d["read"][key].splitlines() if "gamescope_output" not in ln)
        d["cmd"]["pacman -Q gamescope-session-cachyos"] = [1, "error: package not found\n"]
        _, res = run(d)
        self.assertEqual(status(res, "Gaming Mode"), SKIP)
        self.assertFalse(any(r.group == "Steam" for r in res))


class Recording(unittest.TestCase):
    def test_unrecorded_question_is_an_error(self):
        with self.assertRaises(KeyError):
            Replay(RAW["lisa"]).read("/etc/never-asked")

    def test_recordings_hold_no_real_home(self):
        for host, d in RAW.items():
            self.assertNotIn("anthony", json.dumps(d), host)


if __name__ == "__main__":
    unittest.main()
