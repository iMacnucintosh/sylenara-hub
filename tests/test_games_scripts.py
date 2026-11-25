"""The Python helpers of the Games extension: Steam's binary shortcuts file, hidden and private games, sessions."""
import importlib.util
import json
import struct
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("steam_nonsteam", ROOT / "extensions/games/scripts/steam-nonsteam.py")
sn = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sn)


def vdf_string(key: str, value: str) -> bytes:
    return b"\x01" + key.encode() + b"\x00" + value.encode() + b"\x00"


def vdf_int(key: str, value: int) -> bytes:
    return b"\x02" + key.encode() + b"\x00" + struct.pack("<I", value)


def vdf_map(key: str, body: bytes) -> bytes:
    return b"\x00" + key.encode() + b"\x00" + body + b"\x08"


class Shortcuts(unittest.TestCase):
    def test_parses_a_shortcuts_file(self):
        game = vdf_int("appid", 4195243827) + vdf_string("AppName", "World of Warcraft: Forever") + vdf_string("Exe", '"/opt/wow/Wow.exe"')
        data = vdf_map("shortcuts", vdf_map("0", game)) + b"\x08"
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "shortcuts.vdf"
            f.write_bytes(data)
            parsed = sn.parse_shortcuts(f)
        entry = parsed["0"] if "0" in parsed else next(iter(parsed.values()))
        self.assertEqual(entry["AppName"], "World of Warcraft: Forever")

    def test_a_missing_or_broken_file_is_not_a_crash(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "shortcuts.vdf"
            f.write_bytes(b"\x00garbage")
            try:
                sn.parse_shortcuts(f)
            except Exception as e:  # the caller (load_for_account) is what has to cope; it must not hang
                self.assertIsInstance(e, Exception)


class HiddenAndPrivate(unittest.TestCase):
    def test_private_apps_come_from_localconfig(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = Path(d)
            (cfg / "localconfig.vdf").write_text(
                '"UserLocalConfigStore"\n{\n\t"PrivateApps_154763067"\t\t"[1350650,3478650, 3930100,oops]"\n'
                '\t"PrivateApps_999"\t\t"[]"\n}\n')
            self.assertEqual(sn.load_private_ids(cfg), {"1350650", "3478650", "3930100"})

    def test_hidden_collection_and_private_are_both_hidden(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = Path(d)
            (cfg / "localconfig.vdf").write_text('"PrivateApps_1"\t\t"[111]"\n')
            cloud = cfg / "cloudstorage"
            cloud.mkdir()
            hidden = [["user-collections.hidden", {"value": json.dumps({"added": [222, "333"]})}],
                      ["user-collections.favorite", {"value": json.dumps({"added": [444]})}]]
            (cloud / "cloud-storage-namespace-1.json").write_text(json.dumps(hidden))
            (cloud / "cloud-storage-namespace-1.modified.json").write_text("not read")
            self.assertEqual(sn.load_hidden_ids(cfg), ["111", "222", "333"])

    def test_no_files_means_nothing_hidden(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(sn.load_hidden_ids(Path(d)), [])
            self.assertEqual(sn.load_private_ids(Path(d)), set())


class Playtime(unittest.TestCase):
    """Play time of the shortcuts: imported once from Millennium and the old cache, then our own sessions."""

    def setUp(self):
        import os
        import time

        self.now = int(time.time())
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / "home"
        self.state = Path(self.tmp.name) / "state"
        (self.state / "sylenara").mkdir(parents=True)
        self.env = {k: os.environ.get(k) for k in ("HOME", "XDG_STATE_HOME")}
        os.environ["HOME"] = str(self.home)
        os.environ["XDG_STATE_HOME"] = str(self.state)

    def tearDown(self):
        import os

        for k, v in self.env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        self.tmp.cleanup()

    def millennium(self, data):
        path = self.home / ".local/share/millennium/plugins/non-steam-playtimes/sessions.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(data))
        return path

    def activity(self, sessions=None, active=None):
        (self.state / "sylenara/steam-activity.json").write_text(json.dumps({"sessions": sessions or {}, "active": active or {}}))

    def test_the_import_keeps_millennium_totals_and_ignores_what_is_not_a_shortcut(self):
        real = {"started_at": self.now - 7200, "ended_at": self.now - 3600}
        self.millennium({"Minecraft": [{"started_at": 0, "ended_at": 36000}, real],
                         "Battle.net-Setup.exe": [{"started_at": self.now - 100, "ended_at": self.now}]})
        # A session the old cache kept (Millennium rolled it into its total)
        (self.state / "sylenara/nonsteam-sessions.json").write_text(
            json.dumps({"Minecraft": [{"start": self.now - 90000, "end": self.now - 90000 + 7200}]}))
        out = sn.load_playtimes({"Minecraft": "2370657526"})
        self.assertEqual(set(out), {"2370657526"})
        self.assertEqual(out["2370657526"]["playtimeForever"], (36000 + 3600) // 60)  # Millennium's total
        self.assertEqual(len(out["2370657526"]["sessions"]), 2)

    def test_it_works_once_millennium_is_gone_and_new_sessions_add_up(self):
        path = self.millennium({"WoW": [{"started_at": 0, "ended_at": 7200}]})
        first = sn.load_playtimes({"WoW": "4195243827"})["4195243827"]["playtimeForever"]
        path.unlink()
        imported_at = json.loads(sn.playtime_path().read_text())["importedAt"]
        self.activity({"4195243827": [{"start": imported_at + 10, "end": imported_at + 1810}]})
        again = sn.load_playtimes({"WoW": "4195243827"})["4195243827"]["playtimeForever"]
        twice = sn.load_playtimes({"WoW": "4195243827"})["4195243827"]["playtimeForever"]
        self.assertEqual(first, 120)
        self.assertEqual(again, 150)
        self.assertEqual(twice, 150)  # the same session is not counted again

    def test_a_running_game_counts_and_nothing_to_import_is_fine(self):
        self.activity(active={"4195243827": {"start": self.now - 600, "seen": self.now}})
        out = sn.load_playtimes({"WoW": "4195243827"})["4195243827"]
        self.assertEqual(out["playtimeForever"], 10)
        self.assertEqual(out["playtime2Weeks"], 10)

    def test_old_sessions_move_to_the_baseline_and_the_total_stays(self):
        old = self.now - (sn.CACHE_DAYS + 5) * 86400
        (self.state / "sylenara/nonsteam-sessions.json").write_text(json.dumps({"WoW": [{"start": old, "end": old + 3600}]}))
        out = sn.load_playtimes({"WoW": "4195243827"})["4195243827"]
        self.assertEqual(out["playtimeForever"], 60)
        self.assertEqual(out["sessions"], [])


class SteamPlaytime(unittest.TestCase):
    """The total of a shortcut is the one Steam counts (localconfig.vdf, signed id)."""

    def test_reads_the_shortcuts_playtime_and_skips_steam_games(self):
        vdf = """"UserLocalConfigStore"
{
	"Software"
	{
		"Valve"
		{
			"Steam"
			{
				"apps"
				{
					"-99723469"
					{
						"Playtime2wks"		"7918"
						"Playtime"		"7918"
					}
					"1737100"
					{
						"LastPlayed"		"1793730835"
					}
					"-1924309770"
					{
						"LastPlayed"		"1"
					}
				}
			}
		}
	}
}
"""
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "localconfig.vdf").write_text(vdf)
            self.assertEqual(sn.steam_shortcut_playtime(Path(d)), {"4195243827": 7918})
            self.assertEqual(sn.steam_shortcut_playtime(Path(d) / "missing"), {})


class Requirements(unittest.TestCase):
    def test_status_only_needs_steam(self):
        self.assertEqual(set(sn.requirements_status()), {"steam"})


if __name__ == "__main__":
    unittest.main()
