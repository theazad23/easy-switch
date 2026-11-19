"""The installer against a throw-away home directory (no systemd, no Steam)."""

import os
import tempfile
import unittest
from pathlib import Path

from easyswitch import manifest
from easyswitch.doctor import Doctor
from easyswitch.install import BACKUP, Installer
from easyswitch.system import System

CONFIG = """
[modes.desk]
description = "Desk"
gamescope_output = "DP-1"
[modes.desk.outputs.DP-1]
enable = true
primary = true
[modes.tv]
gamescope_output = "HDMI-A-1"
[modes.tv.outputs.HDMI-A-1]
enable = true
primary = true
"""


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = self.tmp.name
        cfg = Path(self.home, ".config/easy-switch/config.toml")
        cfg.parent.mkdir(parents=True)
        cfg.write_text(CONFIG)
        self.ran = []
        self.lines = []

    def tearDown(self):
        self.tmp.cleanup()

    def install(self, nvidia, dry=False):
        i = Installer(self.home, nvidia, dry, runner=lambda c: self.ran.append(c) or 0, out=self.lines.append)
        i.run()
        return i

    def p(self, dest):
        return Path(self.home + dest[1:])


class Install(Base):
    def test_links_point_into_the_repo(self):
        self.install(nvidia=False)
        d = self.p("~/.local/bin/gaming-mode-stopped")
        self.assertTrue(d.is_symlink())
        self.assertEqual(os.readlink(d), str(manifest.GM / "bin/gaming-mode-stopped"))
        self.assertTrue(os.access(d, os.X_OK))

    def test_desktop_entries_carry_the_real_home(self):
        self.install(nvidia=False)
        text = self.p("~/.local/share/applications/gaming-mode-restart.desktop").read_text()
        self.assertIn(f"Exec={self.home}/.local/bin/easy-switch", text)
        self.assertNotIn("@HOME@", text)

    def test_no_placeholder_left_in_any_linked_file(self):
        for it in manifest.items():
            if it.how == "link":
                self.assertNotIn("@HOME@", it.src.read_text(), it.src)

    def test_one_launcher_per_mode(self):
        self.install(nvidia=False)
        tv = self.p("~/.local/share/applications/easy-switch-tv.desktop").read_text()
        self.assertIn("easy-switch tv", tv)
        self.assertIn("Icon=video-television", tv)
        self.assertTrue(self.p("~/.local/share/applications/easy-switch-desk.desktop").exists())

    def test_second_run_changes_nothing(self):
        self.install(nvidia=True)
        self.assertEqual(self.install(nvidia=True).changed, 0)

    def test_dry_run_touches_nothing(self):
        i = self.install(nvidia=True, dry=True)
        self.assertGreater(i.changed, 10)
        self.assertFalse(self.p("~/.local/bin").exists())
        self.assertEqual(self.ran, [])

    def test_services(self):
        self.install(nvidia=False)
        flat = [" ".join(c) for c in self.ran]
        self.assertIn("systemctl --user daemon-reload", flat)
        self.assertIn("systemctl --user mask cachyos-gamescope-autologin.service", flat)
        self.assertTrue(any("enable steam.service" in c for c in flat))


class OldInstall(Base):
    """What the copying installer left behind."""

    def test_identical_copy_becomes_a_link_without_backup(self):
        d = self.p("~/.local/bin/gaming-mode-hdmi-link")
        d.parent.mkdir(parents=True)
        d.write_bytes((manifest.GM / "bin/gaming-mode-hdmi-link").read_bytes())
        self.install(nvidia=False)
        self.assertTrue(d.is_symlink())
        self.assertFalse(Path(str(d) + BACKUP).exists())

    def test_old_unit_with_home_written_in_is_the_same_file(self):
        d = self.p("~/.config/systemd/user/gaming-mode-diag.service")
        d.parent.mkdir(parents=True)
        d.write_text((manifest.GM / "systemd/user/gaming-mode-diag.service").read_text().replace("%h", self.home))
        self.install(nvidia=False)
        self.assertTrue(d.is_symlink())
        self.assertFalse(Path(str(d) + BACKUP).exists())

    def test_older_generated_launcher_is_replaced_without_backup(self):
        d = self.p("~/.local/share/applications/easy-switch-tv.desktop")
        d.parent.mkdir(parents=True)
        d.write_text("[Desktop Entry]\nName=old\n")
        self.install(nvidia=False)
        self.assertIn("easy-switch tv", d.read_text())
        self.assertFalse(Path(str(d) + BACKUP).exists())

    def test_differing_copy_is_kept_once(self):
        d = self.p("~/.local/bin/gaming-mode-diag")
        d.parent.mkdir(parents=True)
        d.write_text("old local version\n")
        self.install(nvidia=False)
        self.assertTrue(d.is_symlink())
        self.assertEqual(Path(str(d) + BACKUP).read_text(), "old local version\n")

    def test_plasma_autostart_steam_is_disabled(self):
        a = self.p("~/.config/autostart/steam.desktop")
        a.parent.mkdir(parents=True)
        a.write_text("[Desktop Entry]\nExec=/usr/bin/steam -silent\n")
        self.install(nvidia=False)
        self.assertFalse(a.exists())
        self.assertTrue(Path(str(a) + BACKUP).exists())

    def test_beta_channel_is_moved_to_the_shared_one(self):
        b = self.p("~/.local/share/Steam/package/beta")
        b.parent.mkdir(parents=True)
        b.write_text("publicbeta")
        self.install(nvidia=False)
        self.assertEqual(b.read_text(), "steamdeck_publicbeta")


class Vendor(Base):
    NV = "~/.local/share/gaming-mode/bin/gamescope"
    DROPIN = "~/.config/systemd/user/gamescope-session.service.d/nvidia.conf"

    def test_nvidia_gets_the_extras(self):
        self.install(nvidia=True)
        self.assertTrue(self.p(self.NV).is_symlink())
        self.assertIn("%h/.local/share/gaming-mode/bin", self.p(self.DROPIN).read_text())

    def test_amd_gets_none(self):
        self.install(nvidia=False)
        self.assertFalse(self.p(self.NV).exists())
        self.assertFalse(self.p(self.DROPIN).exists())

    def test_card_swap_nvidia_to_amd_removes_them_but_keeps_a_copy(self):
        self.install(nvidia=True)
        self.install(nvidia=False)
        self.assertFalse(self.p(self.NV).exists())
        self.assertFalse(self.p(self.DROPIN).exists())
        kept = list(self.p("~/.local/state/easy-switch/removed").glob("*/nvidia.conf"))
        self.assertEqual(len(kept), 1)


class WithDoctor(Base):
    def files_report(self, nvidia):
        s = System()
        s.home = self.home
        d = Doctor.__new__(Doctor)
        d.sys, d.results, d.group, d.config = s, [], "", {"modes": {"desk": {}, "tv": {}}}
        d.vendors = {"nvidia"} if nvidia else {"amd"}
        d.check_files()
        return {r.name: r for r in d.results}

    def test_doctor_agrees_after_install(self):
        for nvidia in (True, False):
            self.install(nvidia=nvidia)
            link = self.p("~/.local/bin/easy-switch")
            if not link.is_symlink():
                link.symlink_to(manifest.REPO / "easy-switch")
            rep = self.files_report(nvidia)
            self.assertEqual(rep["files"].status, "ok", rep)
            self.assertNotIn("launcher for tv", rep)


if __name__ == "__main__":
    unittest.main()
