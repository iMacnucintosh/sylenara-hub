#!/usr/bin/env python3
"""Local Steam library helpers for Sylenara.

Reads Non-Steam shortcuts (shortcuts.vdf) and the hidden library collection
(user-collections.hidden). The hours of the shortcuts come from the extension's own
sessions: steam-activity.py records them (Steam launches a shortcut with
`reaper AppId=<its id>`), and they are folded here into nonsteam-playtime.json, which
keeps them for good. The play time counted before (by the Millennium Non-Steam Playtimes
plugin, which this extension used to read) is imported once into that file.

Usage:
  steam-nonsteam.py [--steamid STEAMID64]

Prints JSON: { "nonSteam": [...], "hiddenAppIds": ["..."] }
"""

from __future__ import annotations

import argparse
import json
import re
import struct
import sys
import time
from pathlib import Path

STEAM64_BASE = 76561197960265728
TWO_WEEKS = 14 * 24 * 60 * 60
CACHE_DAYS = 400


def steam_roots() -> list[Path]:
    home = Path.home()
    roots = [
        home / ".local/share/Steam",
        home / ".steam/steam",
        home / ".steam/root",
        home / ".var/app/com.valvesoftware.Steam/data/Steam",
    ]
    seen: set[Path] = set()
    out: list[Path] = []
    for r in roots:
        try:
            r = r.resolve()
        except OSError:
            continue
        if r.is_dir() and r not in seen:
            seen.add(r)
            out.append(r)
    return out


def account_id(steamid64: str | None) -> str | None:
    if not steamid64 or not steamid64.isdigit():
        return None
    n = int(steamid64)
    if n < STEAM64_BASE:
        return None
    return str(n - STEAM64_BASE)


def parse_map(buf: bytes, i: int) -> tuple[dict, int]:
    out: dict = {}
    while i < len(buf):
        t = buf[i]
        i += 1
        if t == 8:
            return out, i
        z = buf.find(b"\x00", i)
        if z < 0:
            return out, len(buf)
        key = buf[i:z].decode("utf-8", "replace")
        i = z + 1
        if t == 0:
            val, i = parse_map(buf, i)
            out[key] = val
        elif t == 1:
            z = buf.find(b"\x00", i)
            out[key] = buf[i:z].decode("utf-8", "replace")
            i = z + 1
        elif t == 2:
            out[key] = struct.unpack_from("<i", buf, i)[0]
            i += 4
        elif t == 7:
            out[key] = struct.unpack_from("<Q", buf, i)[0]
            i += 8
        else:
            return out, i
    return out, i


def parse_shortcuts(path: Path) -> dict:
    data = path.read_bytes()
    if not data:
        return {}
    if data[0] != 0:
        return {}
    z = data.find(b"\x00", 1)
    if z < 0:
        return {}
    return parse_map(data, z + 1)[0]


def file_url(path: Path | None) -> str:
    if not path or not path.is_file():
        return ""
    return path.resolve().as_uri()


def pick_art(grid: Path, app_id: str, names: list[str]) -> str:
    for name in names:
        url = file_url(grid / name.format(id=app_id))
        if url:
            return url
    return ""


def state_dir() -> Path:
    import os

    return Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local/state") / "sylenara"


def playtime_path() -> Path:
    return state_dir() / "nonsteam-playtime.json"


def read_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def write_json(path: Path, data: object) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data), encoding="utf-8")
        tmp.replace(path)
    except OSError:
        pass


def clean_spans(spans: object) -> list[dict[str, int]]:
    """Sessions with a real start (Millennium's roll-up has started_at=0), one per start, longest end."""
    by_start: dict[int, int] = {}
    for s in spans if isinstance(spans, list) else []:
        if not isinstance(s, dict):
            continue
        try:
            start = int(s.get("start", s.get("started_at")) or 0)
            end = int(s.get("end", s.get("ended_at")) or 0)
        except (TypeError, ValueError):
            continue
        if start > 0 and end > start:
            by_start[start] = max(end, by_start.get(start, 0))
    return [{"start": a, "end": b} for a, b in sorted(by_start.items())]


def import_previous(names: dict[str, str]) -> dict:
    """The play time counted before this extension tracked the shortcuts itself, once: Millennium's
    Non-Steam Playtimes (total per game, with sessions older than two weeks rolled into one) and the
    sessions this extension cached from it (nonsteam-sessions.json). The known sessions are kept; the
    hours with no detail become the game's `baseline`, so its total matches. Works when Millennium is
    gone (then only the cache, or nothing). `names`: shortcut name -> app id."""
    home = Path.home()
    millennium = {}
    for path in (home / ".local/share/millennium/plugins/non-steam-playtimes/sessions.json",
                 home / ".local/share/Steam/plugins/non-steam-playtimes/sessions.json",
                 home / ".steam/steam/plugins/non-steam-playtimes/sessions.json"):
        data = read_json(path)
        if isinstance(data, dict):
            millennium = data
            break
    cache = read_json(state_dir() / "nonsteam-sessions.json")
    cache = cache if isinstance(cache, dict) else {}

    games: dict[str, dict] = {}
    for name, app_id in names.items():
        spans = clean_spans((cache.get(name) or []) + (millennium.get(name) or []))
        known = sum(s["end"] - s["start"] for s in spans)
        total = 0
        for s in millennium.get(name) or []:
            try:
                total += max(0, int(s.get("ended_at") or 0) - int(s.get("started_at") or 0))
            except (TypeError, ValueError, AttributeError):
                pass
        if spans or total:
            games[app_id] = {"name": name, "baseline": max(0, total - known), "sessions": spans}
    return {"version": 1, "importedAt": int(time.time()), "games": games}


def own_sessions() -> tuple[dict[str, list[dict[str, int]]], dict[str, dict[str, int]]]:
    """The sessions steam-activity.py recorded ({app id: [{start, end}]}) and the ones running now."""
    data = read_json(state_dir() / "steam-activity.json")
    data = data if isinstance(data, dict) else {}
    sessions = {k: clean_spans(v) for k, v in (data.get("sessions") or {}).items()}
    active = {}
    for k, v in (data.get("active") or {}).items():
        try:
            active[k] = {"start": int(v["start"]), "end": int(v["seen"])}
        except (KeyError, TypeError, ValueError):
            pass
    return sessions, active


def load_playtimes(names: dict[str, str]) -> dict[str, dict]:
    """{app id: {playtimeForever, playtime2Weeks, lastPlayed, sessions}} (minutes, unix) of the shortcuts.

    nonsteam-playtime.json keeps every session for good (imported once, then the new ones from
    steam-activity.py, which forgets them after a while); sessions older than CACHE_DAYS go into the
    game's baseline, so the total never drops."""
    path = playtime_path()
    store = read_json(path)
    if not isinstance(store, dict) or not isinstance(store.get("games"), dict):
        store = import_previous(names)
    games: dict[str, dict] = store["games"]
    imported_at = int(store.get("importedAt") or 0)

    now = int(time.time())
    horizon = now - CACHE_DAYS * 24 * 60 * 60
    recorded, active = own_sessions()
    for app_id, name in ((i, n) for n, i in names.items()):
        g = games.setdefault(app_id, {"name": name, "baseline": 0, "sessions": []})
        g["name"] = name
        # What was counted before the import is already in it
        fresh = [s for s in recorded.get(app_id, []) if s["start"] >= imported_at]
        spans = clean_spans(g.get("sessions", []) + fresh)
        old = [s for s in spans if s["end"] < horizon]
        g["baseline"] = int(g.get("baseline") or 0) + sum(s["end"] - s["start"] for s in old)
        g["sessions"] = [s for s in spans if s["end"] >= horizon]
    if store != read_json(path):
        write_json(path, store)

    out: dict[str, dict] = {}
    cutoff = now - TWO_WEEKS
    for app_id in names.values():
        g = games.get(app_id) or {}
        spans = list(g.get("sessions") or [])
        live = active.get(app_id)
        if live and live["end"] > live["start"]:
            spans.append(live)
        out[app_id] = {
            "playtimeForever": (int(g.get("baseline") or 0) + sum(s["end"] - s["start"] for s in spans)) // 60,
            "playtime2Weeks": sum(s["end"] - s["start"] for s in spans if s["start"] > cutoff) // 60,
            "lastPlayed": max((s["end"] for s in spans), default=0),
            "sessions": sorted((s for s in spans if s["end"] - s["start"] >= 60), key=lambda s: s["start"], reverse=True),
        }
    return out


def load_private_ids(cfg: Path) -> set[str]:
    """Games marked as private in the library ("Manage → Set as private"): Steam keeps them in
    localconfig.vdf as "PrivateApps_<account>" "[id,id,…]"."""
    try:
        text = (cfg / "localconfig.vdf").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return set()
    ids: set[str] = set()
    for m in re.finditer(r'"PrivateApps_\d+"\s+"\[([^\]]*)\]"', text):
        ids.update(x.strip() for x in m.group(1).split(",") if x.strip().isdigit())
    return ids


def load_hidden_ids(cfg: Path) -> list[str]:
    """Games that must not show: the Hidden collection and the private ones."""
    cloud = cfg / "cloudstorage"
    ids: set[str] = load_private_ids(cfg)
    if not cloud.is_dir():
        return sorted(ids)
    for path in sorted(cloud.glob("cloud-storage-namespace-*.json")):
        if path.name.endswith(".modified.json"):
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        entries = data if isinstance(data, list) else []
        for item in entries:
            if not (isinstance(item, list) and len(item) >= 2):
                continue
            if item[0] != "user-collections.hidden":
                continue
            meta = item[1] if isinstance(item[1], dict) else {}
            raw = meta.get("value") or ""
            try:
                coll = json.loads(raw) if isinstance(raw, str) else raw
            except json.JSONDecodeError:
                continue
            for app in coll.get("added") or []:
                ids.add(str(app))
    return sorted(ids)


def shortcut_id(entry: dict) -> str | None:
    try:
        return str(int(entry.get("appid", 0)) & 0xFFFFFFFF)
    except (TypeError, ValueError):
        return None


def load_for_account(root: Path, acct: str) -> tuple[list[dict], list[str]]:
    cfg = root / "userdata" / acct / "config"
    hidden = load_hidden_ids(cfg)
    vdf = cfg / "shortcuts.vdf"
    if not vdf.is_file():
        return [], hidden
    grid = cfg / "grid"
    shortcuts = parse_shortcuts(vdf)
    names = {(e.get("AppName") or "").strip(): i for e in shortcuts.values()
             if isinstance(e, dict) and (e.get("AppName") or "").strip() and (i := shortcut_id(e))}
    playtimes = load_playtimes(names)
    games: list[dict] = []
    for entry in shortcuts.values():
        if not isinstance(entry, dict):
            continue
        name = (entry.get("AppName") or "").strip()
        if not name:
            continue
        if entry.get("IsHidden") == 1:
            continue
        app_id = shortcut_id(entry)
        if not app_id:
            continue
        icon = entry.get("icon") or ""
        icon_url = file_url(Path(icon)) if icon else ""
        header = pick_art(
            grid,
            app_id,
            ["{id}_hero.jpg", "{id}_hero.png", "{id}.png", "{id}.jpg"],
        )
        capsule = pick_art(
            grid,
            app_id,
            ["{id}p.jpg", "{id}p.png", "{id}.png", "{id}.jpg", "{id}_logo.png"],
        )
        if not capsule:
            capsule = icon_url
        if not header:
            header = capsule or icon_url
        last = entry.get("LastPlayTime") or 0
        try:
            last = int(last)
        except (TypeError, ValueError):
            last = 0
        pt = playtimes.get(app_id) or {}
        if pt.get("lastPlayed"):
            last = max(last, int(pt["lastPlayed"]))
        games.append(
            {
                "appId": app_id,
                "name": name,
                "exe": (entry.get("Exe") or "").strip('"'),
                "icon": icon_url,
                "capsuleUrl": capsule,
                "headerUrl": header,
                "lastPlayed": last,
                "playtimeForever": int(pt.get("playtimeForever") or 0),
                "playtime2Weeks": int(pt.get("playtime2Weeks") or 0),
                "sessions": pt.get("sessions") or [],
                "tracked": True,
                "nonSteam": True,
            }
        )
    games.sort(key=lambda g: g["lastPlayed"], reverse=True)
    return games, hidden


def requirements_status() -> dict:
    """What the extension can use on this machine: Steam (a userdata folder). Only looks; installs nothing."""
    return {"steam": any((r / "userdata").is_dir() for r in steam_roots())}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--steamid", default="")
    ap.add_argument("--status", action="store_true", help="print what is installed (Steam)")
    args = ap.parse_args()
    if args.status:
        json.dump(requirements_status(), sys.stdout)
        sys.stdout.write("\n")
        return 0
    acct = account_id(args.steamid.strip() or None)
    games: list[dict] = []
    hidden: list[str] = []
    for root in steam_roots():
        if acct:
            games, hidden = load_for_account(root, acct)
            if games or hidden:
                break
        else:
            userdata = root / "userdata"
            if not userdata.is_dir():
                continue
            for child in sorted(userdata.iterdir()):
                if child.is_dir() and child.name.isdigit():
                    games, hidden = load_for_account(root, child.name)
                    if games or hidden:
                        break
            if games or hidden:
                break
    json.dump({"nonSteam": games, "hiddenAppIds": hidden}, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
