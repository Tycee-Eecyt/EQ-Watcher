#!/usr/bin/env python3
import json
import math
import os
import platform
import shutil
import sys
from datetime import datetime, timedelta
import queue
import re
import socket
import subprocess
import threading
import time
import uuid
import wave
import webbrowser
import zipfile
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener
from zoneinfo import ZoneInfo


APP_NAME = "EQ Watcher"
APP_VERSION = "1.0.0"
GITHUB_REPOSITORY = "Tycee-Eecyt/EQ-Watcher"
GITHUB_RELEASES_URL = f"https://github.com/{GITHUB_REPOSITORY}/releases"
GITHUB_LATEST_RELEASE_API = f"https://api.github.com/repos/{GITHUB_REPOSITORY}/releases/latest"
APP_DIR = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"
CONFIG_PATH = DATA_DIR / "config.json"
SPELL_CATALOG_PATH = DATA_DIR / "p99_spell_catalog.json"
XDG_CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config"))
AUTOSTART_PATH = XDG_CONFIG_DIR / "autostart" / "eq-watcher.desktop"
WINDOWS_STARTUP_DIR = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
WINDOWS_AUTOSTART_PATH = WINDOWS_STARTUP_DIR / "EQ Watcher.cmd"
APP_LAUNCHER_PATH = APP_DIR / ("EQ-Watcher.exe" if os.name == "nt" else "run-linux-gina.sh")
DEFAULT_PORT = 8765
SCOUT_TIMER_URL = "https://pigparse.azurewebsites.net/api/rolltimer/timers/Green"
SCOUT_TIMER_CACHE_SECONDS = 60
SCOUT_RESPAWN_SECONDS = 10 * 60 * 60
SCOUT_OVERLAY_WINDOW_SECONDS = 30 * 60
RING8_OVERLAY_WINDOW_SECONDS = 30 * 60
EASTERN_TIMEZONE_NAME = "America/New_York"
EASTERN_TIMEZONE = ZoneInfo(EASTERN_TIMEZONE_NAME)
ROLL_OVERLAY_SECONDS = 5 * 60
# EverQuest advances one in-game minute every three real-world seconds.  This
# reference was captured from P99's /time output at the start of 1:00 PM game
# time, keeping the overlay clock aligned without polling or sending data.
EQ_CLOCK_REFERENCE_REAL_TIMESTAMP = 1788146040.0
EQ_CLOCK_REFERENCE_GAME_MINUTES = 13 * 60
EQ_REAL_SECONDS_PER_GAME_MINUTE = 3
SPELLBOOK_NAME_ALIASES = {
    # The P99 class list uses "Subvention" while the Titanium client exports
    # the actual spell name as "Subversion".
    "rapacious subversion": "rapacious subvention",
}

# EQCM's default Raid Kit. These are common items raiders check before an
# event; this is intentionally not a claim that the items drop from raid mobs.
COMMON_RAID_KIT_ITEMS = {
    "vial of velium vapors",
    "leatherfoot raider skullcap",
    "shiny brass idol",
    "ring of shadows",
    "reaper of the dead",
    "pearl",
    "peridot",
    "mana battery - class five",
    "mana battery - class four",
    "mana battery - class three",
    "mana battery - class two",
    "mana battery - class one",
    "10 dose potion of stinging wort",
    "pegasus feather cloak",
    "larrikan's mask",
}


class NoRedirectHandler(HTTPRedirectHandler):
    """Keep the read-only PigParse request pinned to its configured endpoint."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


PIGPARSE_READ_OPENER = build_opener(NoRedirectHandler())
NPARSE_DIR = Path.home() / "nparse"
NPARSE_DATA_DIR = NPARSE_DIR / "data" / "maps"
NPARSE_CONFIG_PATH = NPARSE_DIR / "nparse.config.json"
DEFAULT_LOG_DIR = Path.home() / "Games" / "EverQuest" / "Logs"
EQ_LOG_DIRS = [
    Path.home() / "Games" / "EverQuest" / "Logs",
    Path.home() / "Games" / "EverQuest-Basic" / "Logs",
    Path("/dev/shm/everquest-clean-cache-EverQuest-Basic/EverQuest/Logs"),
    Path("/dev/shm/everquest-clean-cache-EverQuest/EverQuest/Logs"),
    Path("/dev/shm/everquest-clean-cache/EverQuest/Logs"),
]
DEFAULT_GINA_IMPORT_DIRS = [
    Path.home() / "Games" / "EverQuest" / "A Folder for GINA",
    Path.home() / "Games" / "EverQuest" / "A Folder for Gamparse",
]

EVENTS = queue.Queue()
GINA_OVERLAY_EVENTS = queue.Queue()
TEXT_OVERLAY_EVENTS = queue.Queue()
NPARSE_SPELLS_EVENTS = queue.Queue()
SCOUT_OVERLAY_EVENTS = queue.Queue()
ROLL_OVERLAY_EVENTS = queue.Queue()
CH_CHAIN_EVENTS = queue.Queue()
DPS_EVENTS = queue.Queue()
AGGRO_EVENTS = queue.Queue()
SCOUT_TIMER_LOCK = threading.Lock()
SCOUT_TIMER_CACHE = {"data": None, "fetched_at": 0.0}
UPDATE_LOCK = threading.Lock()
UPDATE_CACHE = {"checked_at": 0.0, "data": None}
ROLL_PENDING = {"name": "", "seen_at": 0.0}
TRIGGER_COUNTERS = {}
TRIGGER_REMINDER_LOCK = threading.Lock()
TRIGGER_REMINDERS = {}
BEEP_MELODY_LOCK = threading.Lock()
BEEP_MELODY_NOTES = {}
BEEP_MELODY_INDEXES = {}
BEEP_MELODY_MEASURES = {}
BEEP_MEASURE_INDEXES = {}
BEEP_ACTIVE_MELODY = None
BEEP_PLAYBACK_NOTE_COUNTS = {
    "midi": 1,
    "musical3": 3,
    "musical": 4,
    "musical8": 8,
    "original_bar": 0,
}
BEEP_PLAYBACK_LOCK = threading.Lock()
BEEP_PLAYBACK_PROCESS = None
BEEP_AUDIO_QUEUE = queue.Queue(maxsize=24)
BEEP_WORKER_LOCK = threading.Lock()
BEEP_AUDIO_WORKER = None
FROG_BEAT_EVENTS = queue.Queue()
GROGGIE_ADVENTURER_FRAME_RECTS = (
    (82, 200, 224, 320),
    (343, 200, 224, 320),
    (621, 200, 224, 320),
    (875, 200, 224, 320),
    (1118, 200, 224, 320),
    (1374, 200, 224, 320),
    (1626, 200, 224, 320),
    (1888, 200, 224, 320),
)
DANCE_CHARACTERS = {
    "fussy": {
        "label": "Fussy",
        "path": DATA_DIR / "assets" / "snes-dancing-fussy-v7.png",
        "frames": 4,
        "dance_order": (0, 1, 2, 3, 2, 1),
        "beat_scale": 0.75,
        "styles": {
            "original": {
                "sources": ((DATA_DIR / "assets" / "snes-dancing-fussy-v7.png", 4),),
                "dance_order": (0, 1, 2, 3),
                "beat_scale": 1.0,
            },
            "new": {
                "sources": ((DATA_DIR / "assets" / "snes-dancing-fussy-happy-jump.png", 4),),
                "dance_order": (0, 1, 2, 3),
                "beat_scale": 0.65,
            },
            "special": {
                "sources": ((DATA_DIR / "assets" / "snes-dancing-fussy-snorkel-surf.png", 4),),
                "dance_order": (0, 1, 2, 3, 2, 1),
                "beat_scale": 0.7,
            },
            "combo": {
                "sources": (
                    (DATA_DIR / "assets" / "snes-dancing-fussy-v7.png", 4),
                    (DATA_DIR / "assets" / "snes-dancing-fussy-happy-jump.png", 4),
                    (DATA_DIR / "assets" / "snes-dancing-fussy-snorkel-surf.png", 4),
                ),
                "dance_order": (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 10, 9),
                "beat_scale": 0.7,
            },
        },
    },
    "enoent": {
        "label": "Enoent",
        "path": DATA_DIR / "assets" / "snes-dancing-enoent.png",
        "frames": 4,
        "dance_order": (1, 0, 2, 1, 3, 1),
        "beat_scale": 0.85,
        "styles": {
            "original": {"dance_order": (0, 1, 2, 3), "beat_scale": 1.0},
            "new": {"dance_order": (1, 0, 2, 1, 3, 1), "beat_scale": 0.85},
            "special": {
                "sources": ((DATA_DIR / "assets" / "snes-dancing-enoent-moonwalk.png", 4),),
                "dance_order": (0, 1, 2, 3, 2, 1),
                "beat_scale": 0.7,
            },
            "bee_special": {
                "sources": ((DATA_DIR / "assets" / "snes-dancing-enoent-bee-butt-shake.png", 4),),
                "dance_order": (0, 1, 2, 3, 2, 1),
                "beat_scale": 0.55,
                "chroma_key": "magenta",
            },
            "stinger_special": {
                "sources": ((DATA_DIR / "assets" / "snes-dancing-enoent-bee-stinger-shake.png", 4),),
                "dance_order": (0, 1, 2, 3, 2, 1),
                "beat_scale": 0.5,
                "chroma_key": "magenta",
            },
            "combo": {
                "sources": (
                    (DATA_DIR / "assets" / "snes-dancing-enoent.png", 4),
                    (DATA_DIR / "assets" / "snes-dancing-enoent-moonwalk.png", 4),
                    (DATA_DIR / "assets" / "snes-dancing-enoent-bee-butt-shake.png", 4, (), "magenta"),
                    (DATA_DIR / "assets" / "snes-dancing-enoent-bee-stinger-shake.png", 4, (), "magenta"),
                ),
                "dance_order": (0, 1, 2, 3, 1, 0, 2, 1, 3, 1, 4, 5, 6, 7, 6, 5, 8, 9, 10, 11, 10, 9, 12, 13, 14, 15, 14, 13),
                "beat_scale": 0.8,
            },
        },
    },
    "yellow_cap_frog": {
        "label": "Groggie",
        "path": DATA_DIR / "assets" / "snes-dancing-frog-yellow-cap.png",
        "frames": 4,
        "dance_order": (0, 2, 1, 3),
        "beat_scale": 1.0,
        "styles": {
            "original": {"dance_order": (0, 1, 2, 3), "beat_scale": 1.0},
            "new": {"dance_order": (0, 2, 1, 3), "beat_scale": 1.0},
            "adventurer": {
                "sources": ((
                    DATA_DIR / "assets" / "snes-dancing-groggie-adventurer-v2.png",
                    8,
                    GROGGIE_ADVENTURER_FRAME_RECTS,
                ),),
                "chroma_key": "magenta",
                "dance_order": (0, 1, 2, 3, 4, 5, 6, 7),
                "beat_scale": 0.72,
            },
            "special": {
                "sources": ((DATA_DIR / "assets" / "snes-dancing-groggie-breakdance.png", 4),),
                "dance_order": (0, 1, 2, 3, 2, 1),
                "beat_scale": 0.65,
            },
            "combo": {
                "sources": (
                    (DATA_DIR / "assets" / "snes-dancing-frog-yellow-cap.png", 4),
                    (DATA_DIR / "assets" / "snes-dancing-groggie-breakdance.png", 4),
                ),
                "dance_order": (0, 1, 2, 3, 0, 2, 1, 3, 1, 0, 1, 2, 3, 2, 4, 5, 6, 7, 6, 5),
                "beat_scale": 0.75,
            },
        },
    },
    "rupert": {
        "label": "Rupert",
        "path": DATA_DIR / "assets" / "snes-dancing-rupert.png",
        "frames": 4,
        "dance_order": (0, 2, 1, 3, 2, 1),
        "beat_scale": 0.8,
        "styles": {
            "original": {"dance_order": (0, 1, 2, 3), "beat_scale": 1.0},
            "new": {"dance_order": (0, 2, 1, 3, 2, 1), "beat_scale": 0.8},
            "special": {
                "sources": ((DATA_DIR / "assets" / "snes-dancing-rupert-headbang.png", 4),),
                "dance_order": (0, 1, 2, 3, 2, 1),
                "beat_scale": 0.55,
            },
            "combo": {
                "sources": (
                    (DATA_DIR / "assets" / "snes-dancing-rupert.png", 4),
                    (DATA_DIR / "assets" / "snes-dancing-rupert-headbang.png", 4),
                ),
                "dance_order": (0, 1, 2, 3, 0, 2, 1, 3, 4, 5, 6, 7, 6, 5),
                "beat_scale": 0.7,
            },
        },
    },
    "adventurer_frog": {
        "label": "Adventurer Frog",
        "path": DATA_DIR / "assets" / "snes-dancing-frog.png",
        "frames": 4,
        "dance_order": (1, 0, 1, 2, 3, 2),
        "beat_scale": 0.9,
        "styles": {
            "original": {"dance_order": (0, 1, 2, 3), "beat_scale": 1.0},
            "new": {"dance_order": (1, 0, 1, 2, 3, 2), "beat_scale": 0.9},
            "combo": {"dance_order": (0, 1, 2, 3, 1, 0, 1, 2, 3, 2), "beat_scale": 0.85},
        },
    },
}
BEEP_MELODIES = {
    "eq_kelethin": {
        "label": "Kelethin / Greater Faydark",
        "format": "xmi",
    },
    "chrono_600ad": {
        "label": "600 A.D. / Wind Scene",
        "path": DATA_DIR / "midi" / "chrono-trigger-600ad.mid",
        "featured_tracks": (3, 13, 14),
    },
    "chrono_theme": {
        "label": "Chrono Trigger Theme",
        "path": DATA_DIR / "midi" / "chrono-trigger-theme.mid",
        "featured_tracks": (1, 2, 3),
    },
    "chrono_schala": {
        "label": "Schala's Theme",
        "path": DATA_DIR / "midi" / "chrono-trigger-schala.mid",
        "featured_tracks": (5, 7, 8),
    },
    "zelda_oot_lost_woods": {
        "label": "Lost Woods / Saria's Song",
        "path": DATA_DIR / "midi" / "zelda-oot-lost-woods.mid",
        "featured_tracks": (5,),
    },
    "zelda_oot_song_of_storms": {
        "label": "Song of Storms",
        "path": DATA_DIR / "midi" / "zelda-oot-song-of-storms.mid",
        "featured_tracks": (4,),
    },
    "zelda_oot_gerudo_valley": {
        "label": "Gerudo Valley",
        "path": DATA_DIR / "midi" / "zelda-oot-gerudo-valley.mid",
        "featured_tracks": (4,),
    },
    "ff_prelude": {
        "label": "Final Fantasy Prelude",
        "path": DATA_DIR / "midi" / "final-fantasy-prelude.mid",
        "featured_tracks": (2, 6),
    },
    "ff_victory": {
        "label": "Final Fantasy Victory Fanfare",
        "path": DATA_DIR / "midi" / "final-fantasy-victory.mid",
        "featured_tracks": (1, 2),
    },
    "ff5_main": {
        "label": "Final Fantasy V Main Theme",
        "path": DATA_DIR / "midi" / "final-fantasy-v-main-theme.mid",
        "featured_tracks": (1, 2, 4),
    },
}
HTTP_SERVER = None
CONFIG_VERSION = 0
OVERLAY_CONTROLLER = None
DPS_LOCK = threading.Lock()
DPS_IDLE_SECONDS = 20
DPS_HISTORY_MAX = 500
MAP_LOCATION_FRESH_SECONDS = 30
STATE = {
    "running": True,
    "active_log": "",
    "character": "",
    "zone": "",
    "zone_key": "",
    "zone_entered_at": 0,
    "location_x": None,
    "location_y": None,
    "location_z": None,
    "location_raw_x": None,
    "location_raw_y": None,
    "location_raw_z": None,
    "last_location_at": 0,
    "heading": "",
    "movement_angle": None,
    "movement_distance": 0.0,
    "last_line": "",
    "last_match": "",
    "started_at": time.time(),
    "ui_url": "",
}


def scout_timer_payload(force=False):
    """Read Scout's public timer without sending any EQ Watcher or player data."""
    now = time.time()
    with SCOUT_TIMER_LOCK:
        cached = SCOUT_TIMER_CACHE.get("data")
        fetched_at = float(SCOUT_TIMER_CACHE.get("fetched_at") or 0)
        if cached and not force and now - fetched_at < SCOUT_TIMER_CACHE_SECONDS:
            return dict(cached)

        try:
            parsed_url = urlparse(SCOUT_TIMER_URL)
            if (
                parsed_url.scheme != "https"
                or parsed_url.hostname != "pigparse.azurewebsites.net"
                or parsed_url.path != "/api/rolltimer/timers/Green"
                or parsed_url.query
                or parsed_url.fragment
                or parsed_url.username
                or parsed_url.password
            ):
                raise ValueError("unsafe PigParse timer URL")

            # Privacy boundary: this is always a bodyless GET to one fixed
            # endpoint. Never attach character, log, zone, config, or app data.
            request = Request(
                SCOUT_TIMER_URL,
                data=None,
                headers={"Accept": "application/json", "User-Agent": ""},
                method="GET",
            )
            with PIGPARSE_READ_OPENER.open(request, timeout=8) as response:
                if response.geturl() != SCOUT_TIMER_URL:
                    raise ValueError("PigParse timer request was redirected")
                timers = json.loads(response.read().decode("utf-8"))
            if not isinstance(timers, list):
                raise ValueError("timer service returned an unexpected response")

            scout = next(
                (
                    item for item in timers
                    if isinstance(item, dict)
                    and str(item.get("name", "")).strip().casefold() == "scout charisa"
                ),
                None,
            )
            if scout is None:
                raise ValueError("Scout Charisa was not found in the Green timers")

            date_time = str(scout.get("dateTime") or "").strip()
            if not date_time:
                raise ValueError("Scout Charisa's timer has no dateTime")
            parsed_time = datetime.fromisoformat(date_time.replace("Z", "+00:00"))
            if parsed_time.tzinfo is None:
                parsed_time = parsed_time.astimezone()
            source_timestamp = parsed_time.timestamp()
            display_timestamp = source_timestamp
            cycles_ahead = 0
            if display_timestamp <= now:
                cycles_ahead = math.floor((now - display_timestamp) / SCOUT_RESPAWN_SECONDS) + 1
                display_timestamp += cycles_ahead * SCOUT_RESPAWN_SECONDS

            payload = {
                "ok": True,
                "name": str(scout.get("name") or "Scout Charisa"),
                "date_time": date_time,
                "timestamp": source_timestamp,
                "display_timestamp": display_timestamp,
                "derived_guess": cycles_ahead > 0,
                "cycles_ahead": cycles_ahead,
                "guess": bool(scout.get("guess", False)),
                "roll_timer_type": scout.get("rollTimerType"),
                "fetched_at": now,
                "stale": False,
                "source": SCOUT_TIMER_URL,
            }
            SCOUT_TIMER_CACHE.update({"data": payload, "fetched_at": now})
            return dict(payload)
        except (HTTPError, URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
            if cached:
                stale = dict(cached)
                stale.update({"stale": True, "error": str(exc)})
                return stale
            return {
                "ok": False,
                "error": str(exc),
                "fetched_at": now,
                "source": SCOUT_TIMER_URL,
            }


def autostart_desktop_entry():
    launcher = str(APP_LAUNCHER_PATH).replace("\\", "\\\\").replace('"', '\\"')
    return (
        "[Desktop Entry]\n"
        "Version=1.0\n"
        "Type=Application\n"
        "Name=EQ Watcher\n"
        "Comment=Start EQ Watcher when you sign in\n"
        f'Exec=env LINUX_GINA_NO_BROWSER=1 "{launcher}"\n'
        "Icon=utilities-system-monitor\n"
        "Terminal=false\n"
        "StartupNotify=false\n"
        "X-GNOME-Autostart-enabled=true\n"
    )


def autostart_enabled():
    if os.name == "nt":
        return WINDOWS_AUTOSTART_PATH.is_file()
    return AUTOSTART_PATH.is_file()


def set_autostart(enabled):
    if os.name == "nt":
        if enabled:
            if not APP_LAUNCHER_PATH.is_file():
                raise FileNotFoundError(f"EQ Watcher executable not found: {APP_LAUNCHER_PATH}")
            WINDOWS_AUTOSTART_PATH.parent.mkdir(parents=True, exist_ok=True)
            WINDOWS_AUTOSTART_PATH.write_text(
                f'@start "" "{APP_LAUNCHER_PATH}"\n', encoding="utf-8"
            )
        else:
            WINDOWS_AUTOSTART_PATH.unlink(missing_ok=True)
        return autostart_enabled()
    if enabled:
        if not APP_LAUNCHER_PATH.is_file():
            raise FileNotFoundError(f"EQ Watcher launcher not found: {APP_LAUNCHER_PATH}")
        AUTOSTART_PATH.parent.mkdir(parents=True, exist_ok=True)
        temp_path = AUTOSTART_PATH.with_suffix(".tmp")
        temp_path.write_text(autostart_desktop_entry(), encoding="utf-8")
        temp_path.chmod(0o644)
        temp_path.replace(AUTOSTART_PATH)
    else:
        AUTOSTART_PATH.unlink(missing_ok=True)
    return autostart_enabled()


def version_tuple(value):
    numbers = re.findall(r"\d+", str(value or ""))[:3]
    return tuple((int(number) for number in numbers)) + (0,) * (3 - len(numbers))


def update_asset_name():
    return "EQ-Watcher-Setup-windows-x64.exe" if os.name == "nt" else "EQ-Watcher-linux-x86_64.tar.gz"


def check_for_update(force=False):
    now = time.time()
    with UPDATE_LOCK:
        cached = UPDATE_CACHE.get("data")
        if cached and not force and now - UPDATE_CACHE.get("checked_at", 0) < 60 * 60:
            return dict(cached)
        request = Request(GITHUB_LATEST_RELEASE_API, headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"EQ-Watcher/{APP_VERSION}",
        })
        try:
            with build_opener().open(request, timeout=8) as response:
                release = json.loads(response.read().decode("utf-8"))
            latest = str(release.get("tag_name") or "").lstrip("v")
            wanted_asset = update_asset_name()
            asset = next((item for item in release.get("assets", []) if item.get("name") == wanted_asset), None)
            payload = {
                "ok": True,
                "current_version": APP_VERSION,
                "latest_version": latest,
                "update_available": bool(latest and version_tuple(latest) > version_tuple(APP_VERSION)),
                "asset_name": wanted_asset,
                "download_url": (asset or {}).get("browser_download_url", ""),
                "release_url": release.get("html_url") or GITHUB_RELEASES_URL,
                "published_at": release.get("published_at", ""),
            }
        except (OSError, HTTPError, URLError, ValueError, json.JSONDecodeError) as exc:
            payload = {
                "ok": False,
                "current_version": APP_VERSION,
                "latest_version": "",
                "update_available": False,
                "download_url": "",
                "release_url": GITHUB_RELEASES_URL,
                "error": str(exc),
            }
        UPDATE_CACHE.update({"checked_at": now, "data": payload})
        return dict(payload)


def scout_overlay_timer(payload, now=None):
    """Build the spell-overlay row while Scout is within the final 30 minutes."""
    if not isinstance(payload, dict) or not payload.get("ok"):
        return None
    try:
        ends = float(payload.get("display_timestamp") or payload.get("timestamp") or 0)
    except (TypeError, ValueError):
        return None
    remaining = ends - (time.time() if now is None else now)
    if remaining <= 0 or remaining > SCOUT_OVERLAY_WINDOW_SECONDS:
        return None
    return {
        "spell_id": "scout-charisa",
        "name": str(payload.get("name") or "Scout Charisa"),
        "color": "#a78bfa",
        "ends": ends,
        "seconds": SCOUT_OVERLAY_WINDOW_SECONDS,
        "scout": True,
    }


def _parse_clock_time(value):
    match = re.fullmatch(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", value, re.IGNORECASE)
    if not match:
        raise ValueError("use a time such as 10:54pm, 22:54, or 8/30 10:54pm")
    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    meridiem = (match.group(3) or "").lower()
    if minute > 59:
        raise ValueError("minutes must be between 00 and 59")
    if meridiem:
        if hour < 1 or hour > 12:
            raise ValueError("12-hour times must use an hour from 1 to 12")
        hour = (hour % 12) + (12 if meridiem == "pm" else 0)
    elif hour > 23:
        raise ValueError("24-hour times must use an hour from 0 to 23")
    return hour, minute


def parse_ring8_time(value, now=None):
    """Parse a user-entered Ring 8 roll time as Eastern time."""
    text = re.sub(r"\s+", " ", str(value or "").strip())
    if not text:
        raise ValueError("enter a Ring 8 roll time")
    text = re.sub(r"\s+(?:est|edt|et)$", "", text, flags=re.IGNORECASE).strip()
    text = re.sub(r"^(\d{4}-\d{1,2}-\d{1,2})[Tt](?=\d)", r"\1 ", text)
    eastern_now = now or datetime.now(EASTERN_TIMEZONE)
    if eastern_now.tzinfo is None:
        eastern_now = eastern_now.replace(tzinfo=EASTERN_TIMEZONE)
    else:
        eastern_now = eastern_now.astimezone(EASTERN_TIMEZONE)

    day_word = re.fullmatch(r"(today|tomorrow)\s+(.+)", text, re.IGNORECASE)
    if day_word:
        day_offset = 1 if day_word.group(1).lower() == "tomorrow" else 0
        hour, minute = _parse_clock_time(day_word.group(2))
        target_date = eastern_now.date() + timedelta(days=day_offset)
        candidate = datetime.combine(target_date, datetime.min.time(), EASTERN_TIMEZONE).replace(
            hour=hour, minute=minute
        )
    else:
        dated = re.fullmatch(
            r"(?:(\d{4})-(\d{1,2})-(\d{1,2})|(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?)\s+(.+)",
            text,
        )
        if dated:
            year_was_explicit = bool(dated.group(1) or dated.group(6))
            if dated.group(1):
                year, month, day = map(int, dated.group(1, 2, 3))
            else:
                month, day = map(int, dated.group(4, 5))
                year_text = dated.group(6)
                year = int(year_text) if year_text else eastern_now.year
                if year < 100:
                    year += 2000
            hour, minute = _parse_clock_time(dated.group(7))
            try:
                candidate = datetime(year, month, day, hour, minute, tzinfo=EASTERN_TIMEZONE)
            except ValueError as exc:
                raise ValueError(f"invalid date: {exc}") from exc
            if not year_was_explicit and candidate <= eastern_now:
                try:
                    candidate = candidate.replace(year=candidate.year + 1)
                except ValueError as exc:
                    raise ValueError(f"invalid date: {exc}") from exc
        else:
            hour, minute = _parse_clock_time(text)
            candidate = eastern_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if candidate <= eastern_now:
                candidate += timedelta(days=1)

    if candidate <= eastern_now:
        raise ValueError("the Ring 8 roll time must be in the future")
    return candidate


def ring8_timer_payload():
    with CONFIG_LOCK:
        stored = dict(CONFIG.get("ring8_timer") or {})
    timestamp = float(stored.get("timestamp") or 0)
    if timestamp <= 0:
        return {
            "ok": True,
            "active": False,
            "timezone": EASTERN_TIMEZONE_NAME,
        }
    eastern_time = datetime.fromtimestamp(timestamp, EASTERN_TIMEZONE)
    return {
        "ok": True,
        "active": True,
        "name": "Ring 8 Roll",
        "input": str(stored.get("input") or ""),
        "timestamp": timestamp,
        "date_time": eastern_time.isoformat(),
        "timezone": EASTERN_TIMEZONE_NAME,
    }


def ring8_overlay_timer(payload=None, now=None):
    payload = ring8_timer_payload() if payload is None else payload
    if not isinstance(payload, dict) or not payload.get("active"):
        return None
    try:
        ends = float(payload.get("timestamp") or 0)
    except (TypeError, ValueError):
        return None
    remaining = ends - (time.time() if now is None else now)
    if remaining <= 0 or remaining > RING8_OVERLAY_WINDOW_SECONDS:
        return None
    return {
        "spell_id": "ring-8-roll",
        "name": "Ring 8 Roll",
        "color": "#f59e0b",
        "ends": ends,
        "seconds": RING8_OVERLAY_WINDOW_SECONDS,
        "ring8": True,
    }

LOG_PREFIX_RE = re.compile(r"^\[[A-Z][a-z]{2} [A-Z][a-z]{2} +\d{1,2} \d{2}:\d{2}:\d{2} \d{4}\] ?")
LOG_TIMESTAMP_RE = re.compile(r"^\[(?P<stamp>[A-Z][a-z]{2} [A-Z][a-z]{2} +\d{1,2} \d{2}:\d{2}:\d{2} \d{4})\]")
LEVEL_GAIN_RE = re.compile(r"You have gained a level! Welcome to level (?P<level>\d+)!", re.IGNORECASE)
ROLL_NAME_RE = re.compile(r"^\*\*A Magic Die is rolled by (?P<name>.+?)\.$", re.IGNORECASE)
ROLL_VALUE_RE = re.compile(
    r"^\*\*It could have been any number from (?P<minimum>-?\d+) to (?P<maximum>-?\d+), "
    r"but this time it turned up a (?P<value>-?\d+)\.$",
    re.IGNORECASE,
)
ZONE_ENTER_RE = re.compile(r"^You have entered (?P<zone>.+?)\.$", re.IGNORECASE)
WHO_COUNT_RE = re.compile(r"^There (?:is|are) \d+ player(?:s)? in (?P<zone>.+?)\.$", re.IGNORECASE)
WHO_ZONE_RE = re.compile(r"^There are no players in (?P<zone>.+?) that match those who filters\.$", re.IGNORECASE)
LOCATION_RE = re.compile(r"^Your Location is (?P<x>-?\d+(?:\.\d+)?), (?P<y>-?\d+(?:\.\d+)?), (?P<z>-?\d+(?:\.\d+)?)$", re.IGNORECASE)
HEADING_RE = re.compile(r"^You think you are heading (?P<heading>.+?)\.$", re.IGNORECASE)
CH_WORD_RE = re.compile(r"\bch\b", re.IGNORECASE)
CH_CHAIN_TAG_RE = re.compile(r"\b(?:GG|LA|CA)\b", re.IGNORECASE)
CH_RCH_RE = re.compile(r"\brch\b", re.IGNORECASE)
CH_RAMP_RE = re.compile(r"\bRAMP(?P<number>\d{1,3})\b", re.IGNORECASE)
CH_NUMERIC_POSITION_RE = re.compile(r"\b(?P<position>\d{3})\b")
CH_LETTER_POSITION_RE = re.compile(r"\b(?P<position>[A-Za-z]{3})\b")
GUILD_CHAT_RE = re.compile(r"\b(?:tells? the guild|say(?:s)? to your guild|told the guild)\b", re.IGNORECASE)
DPS_VERBS = (
    "hit",
    "hits",
    "slash",
    "slashes",
    "crush",
    "crushes",
    "pierce",
    "pierces",
    "kick",
    "kicks",
    "bash",
    "bashes",
    "backstab",
    "backstabs",
    "punch",
    "punches",
    "bite",
    "bites",
    "slice",
    "slices",
    "claw",
    "claws",
    "strike",
    "strikes",
    "gore",
    "gores",
    "maul",
    "mauls",
)
DPS_DAMAGE_RE = re.compile(
    rf"^(?P<attacker>.+?)\s+(?P<verb>{'|'.join(DPS_VERBS)})\s+(?P<target>.+?)\s+for\s+(?P<damage>\d+)\s+points?\s+of\s+damage\.$",
    re.IGNORECASE,
)
DPS_NON_MELEE_RE = re.compile(
    r"^.+? was hit by non-melee for \d+ points? of damage\.$",
    re.IGNORECASE,
)
DPS_SLAIN_RE = re.compile(r"^(?P<target>.+?) has been slain by (?P<killer>.+?)!$", re.IGNORECASE)
DPS_STATE = {
    "target": "",
    "start_ts": 0,
    "last_ts": 0,
    "ended_ts": 0,
    "active": False,
    "total_damage": 0,
    "combatants": {},
    "hits": {},
    "proc_counts": {},
    "last_killer": "",
    "encounter_id": "",
}
DPS_HISTORY = []
AGGRO_LOCK = threading.Lock()
AGGRO_IDLE_SECONDS = 20
AGGRO_MISS_RE = re.compile(
    r"^You try to (?P<verb>hit|slash|crush|pierce|punch|kick|bash) (?P<target>.+?), but .+!$",
    re.IGNORECASE,
)
AGGRO_CAST_RE = re.compile(r"^You begin casting (?P<spell>Flame Lick|Enveloping Roots|Jolt|Cinder Jolt)\.$", re.IGNORECASE)
AGGRO_WHO_RE = re.compile(r"^\[(?P<level>\d+) (?P<title>[^\]]+)\]\s+(?P<name>[A-Za-z][A-Za-z']*)\b")
AGGRO_ANY_MISS_RE = re.compile(
    r"^(?P<attacker>.+?) (?:try|tries) to (?P<verb>hit|slash|crush|pierce|punch|kick|bash) (?P<target>.+?), but .+!$",
    re.IGNORECASE,
)
AGGRO_TITLE_CLASSES = {
    "warlord": "Warrior",
    "champion": "Warrior",
    "grandmaster": "Monk",
    "master": "Monk",
    "assassin": "Rogue",
    "grave lord": "Shadow Knight",
    "oracle": "Shaman",
    "virtuoso": "Bard",
    "high priest": "Cleric",
    "templar": "Cleric",
    "vicar": "Cleric",
    "sorcerer": "Wizard",
    "phantasmist": "Enchanter",
    "hierophant": "Druid",
    "preserver": "Ranger",
    "archon": "Paladin",
    "warlock": "Necromancer",
    "conjurer": "Magician",
}
AGGRO_CLASS_SWING_THREAT = {
    "Warrior": 25,
    "Monk": 23,
    "Rogue": 24,
    "Shadow Knight": 25,
    "Paladin": 25,
    "Ranger": 24,
    "Bard": 22,
    "Shaman": 18,
    "Druid": 17,
    "Cleric": 18,
    "Wizard": 15,
    "Enchanter": 15,
    "Necromancer": 17,
    "Magician": 15,
}
# Weapon values and proc messages mirror CCHPM's bundled weapon profiles.
AGGRO_WEAPON_PROFILES = {
    "swiftblade of zek": {"damage": 11, "type": "slash"},
    "blade of tactics": {"damage": 14, "type": "slash"},
    "blade of strategy": {
        "damage": 14, "type": "slash", "proc_threat": 600,
        "proc_resist": "your target resisted the rage of vallon spell.",
        "proc_land": "is weakened by the rage of vallon.",
    },
    "willsapper": {
        "damage": 13, "type": "pierce", "proc_threat": 400,
        "proc_resist": "your target resisted the energy sap spell.",
        "proc_land": "yawns.",
    },
    "jagged blade of war": {
        "damage": 36, "damage_bonus": 34, "type": "slash", "two_handed": True,
        "proc_threat": 675, "proc_resist": "your target resisted the rage of zek spell.",
        "proc_land": "soul is consumed by the fury of zek.",
    },
    "howling cutlass": {
        "damage": 10, "type": "slash", "proc_threat": 520,
        "proc_resist": "your target resisted the shrieking howl spell.",
        "proc_land": "is deafened.",
    },
    "trident of the deep sea": {
        "damage": 14, "type": "pierce", "proc_threat": 400,
        "proc_resist": "your target resisted the waves of the deep sea spell.",
        "proc_land": "is crushed by a wall of water.",
    },
    "earthcaller": {
        "damage": 14, "type": "slash", "proc_threat": 400,
        "proc_resist": "your target resisted the earthcall spell.",
        "proc_land": "is slowed by the embracing earth.",
    },
}
AGGRO_CLASS_CACHE = {}
AGGRO_INVENTORY_CACHE = {"character": "", "path": "", "mtime": 0, "primary": None, "secondary": None}
AGGRO_STATE = {
    "target": "",
    "start_ts": 0,
    "last_ts": 0,
    "active": False,
    "threat": {},
    "actions": {},
    "procs": {},
    "pending_spell": "",
    "pending_spell_ts": 0,
}


DEFAULT_CONFIG = {
    "log_dir": str(DEFAULT_LOG_DIR),
    "active_log": "",
    "follow_latest": True,
    "favorite_characters": [],
    "show_favorites_only": False,
    "speak": True,
    "voice_type": "",
    "voice_rate": 0,
    "voice_pitch": 0,
    "voice_volume": 100,
    "beep": True,
    "beep_volume": 100,
    "beep_melody": "chrono_600ad",
    "beep_playback": "midi",
    "desktop_notifications": False,
    "launch_at_startup": False,
    "automatic_update_checks": False,
    "ring8_timer": {
        "input": "",
        "timestamp": 0,
        "timezone": EASTERN_TIMEZONE_NAME,
    },
    "overlay": {
        "enabled": True,
        "edit_mode": False,
        "click_through": True,
        "x": 1240,
        "y": 120,
        "width": 320,
        "scale": 100,
        "opacity": 86,
        "max_timers": 8,
    },
    "nparse": {
        "discord": {
            "bg_opacity": 25,
            "clickthrough": False,
            "color": "#000000",
            "geometry": [0, 400, 200, 400],
            "opacity": 80,
            "toggled": False,
            "url": "",
        },
        "maps": {
            "auto_follow": True,
            "center_character_location": False,
            "closest_z_alpha": 20,
            "clickthrough": False,
            "color": "#000000",
            "current_z_alpha": 100,
            "geometry": [247, 54, 349, 299],
            "grid_line_width": 1,
            "hide_when_location_stale": True,
            "line_width": 1,
            "show_grid": True,
            "show_mouse_location": True,
            "show_poi": True,
            "opacity": 80,
            "other_z_alpha": 10,
            "scale": 0.01947098754708777,
            "selected_zone": "",
            "toggled": False,
            "use_z_layers": False,
        },
        "text_overlay": {
            "always_on_top": True,
            "clickthrough": True,
            "color": "#000000",
            "duration_seconds": 4,
            "frameless": True,
            "geometry": [520, 180, 520, 110],
            "opacity": 78,
            "show_all_triggers": False,
            "toggled": True,
        },
        "nparse_spells": {
            "always_on_top": True,
            "clickthrough": False,
            "color": "#000000",
            "frameless": True,
            "geometry": [400, 0, 240, 420],
            "opacity": 80,
            "toggled": False,
        },
        "rolls": {
            "always_on_top": True,
            "clickthrough": True,
            "color": "#000000",
            "frameless": True,
            "geometry": [650, 120, 300, 260],
            "opacity": 82,
            "toggled": True,
        },
        "frog_dancer": {
            "always_on_top": True,
            "character": "yellow_cap_frog",
            "dance_style": "new",
            "clickthrough": True,
            "color": "#000000",
            "frameless": True,
            "geometry": [1660, 700, 180, 180],
            "opacity": 100,
            "toggled": True,
        },
        "ch_chain": {
            "cast_seconds": 10,
            "clickthrough": True,
            "color": "#000000",
            "filter_mode": "recent_current_or_guild",
            "frameless": True,
            "guild_only": False,
            "geometry": [611, 151, 714, 105],
            "landed_grace_seconds": 1.0,
            "max_slots": 8,
            "metronome": True,
            "opacity": 18,
            "post_chain_visible_seconds": 0,
            "recent_seconds": 300,
            "tag_filter": "",
            "ttl_seconds": 60,
            "toggled": True,
        },
        "dps": {
            "cycle_enabled": False,
            "cycle_seconds": 8,
            "clickthrough": True,
            "color": "#000000",
            "custom_end_ts": 0,
            "custom_start_ts": 0,
            "filter_preset": "all",
            "frameless": True,
            "geometry": [920, 420, 340, 300],
            "lock_geometry": True,
            "max_rows": 10,
            "opacity": 72,
            "selected_encounter_id": "",
            "toggled": False,
        },
        "aggro": {
            "clickthrough": True,
            "color": "#000000",
            "frameless": True,
            "geometry": [1260, 420, 320, 270],
            "lock_height_on_width_resize": True,
            "max_rows": 8,
            "opacity": 76,
            "toggled": True,
        },
        "spells": {
            "casting_window_buffer": 1000,
            "clickthrough": False,
            "color": "#000000",
            "custom_timers": [],
            "delay_self_buffs_on_zone": True,
            "geometry": [400, 0, 200, 400],
            "level": 1,
            "opacity": 80,
            "show_clear_buttons": False,
            "toggled": False,
            "use_casting_window": True,
            "use_custom_triggers": True,
            "use_item_triggers": False,
            "use_secondary": ["levitate"],
            "use_secondary_all": False,
        },
    },
    "triggers": [
        {
            "id": "example-root",
            "name": "Root Break",
            "pattern": "Your .* spell has worn off",
            "message": "Root broke",
            "timer_seconds": 0,
            "color": "#f97316",
            "enabled": True,
        },
        {
            "id": "example-invis",
            "name": "Invis Fading",
            "pattern": "You feel yourself starting to appear",
            "message": "Invis is fading",
            "timer_action": "stop",
            "timer_target": "Invisibility",
            "timer_seconds": 0,
            "color": "#38bdf8",
            "enabled": True,
        },
        {
            "id": "example-gather-shadows",
            "name": "Gather Shadows Broken",
            "pattern": "Your shadows fade",
            "message": "Gather Shadows broke",
            "timer_action": "stop",
            "timer_target": "Gather Shadows",
            "timer_seconds": 0,
            "color": "#a78bfa",
            "enabled": True,
        },
        {
            "id": "example-jboots",
            "name": "Journeyman Boots",
            "pattern": "Your feet feel quick",
            "message": "Jboots",
            "timer_seconds": 1080,
            "color": "#22c55e",
            "enabled": True,
        },
    ],
}


def load_config():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFIG_PATH.exists():
        save_config(DEFAULT_CONFIG)
        return dict(DEFAULT_CONFIG)
    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        config = json.load(f)
    merged = dict(DEFAULT_CONFIG)
    merged.update(config)
    merged["overlay"] = dict(DEFAULT_CONFIG["overlay"])
    merged["overlay"].update(config.get("overlay", {}))
    merged["ring8_timer"] = dict(DEFAULT_CONFIG["ring8_timer"])
    merged["ring8_timer"].update(config.get("ring8_timer", {}))
    merged["nparse"] = dict(DEFAULT_CONFIG["nparse"])
    merged["nparse"]["discord"] = dict(DEFAULT_CONFIG["nparse"]["discord"])
    merged["nparse"]["discord"].update(config.get("nparse", {}).get("discord", {}))
    merged["nparse"]["maps"] = dict(DEFAULT_CONFIG["nparse"]["maps"])
    merged["nparse"]["maps"].update(config.get("nparse", {}).get("maps", {}))
    merged["nparse"]["text_overlay"] = dict(DEFAULT_CONFIG["nparse"]["text_overlay"])
    merged["nparse"]["text_overlay"].update(config.get("nparse", {}).get("text_overlay", {}))
    merged["nparse"]["nparse_spells"] = dict(DEFAULT_CONFIG["nparse"]["nparse_spells"])
    merged["nparse"]["nparse_spells"].update(config.get("nparse", {}).get("nparse_spells", {}))
    merged["nparse"]["rolls"] = dict(DEFAULT_CONFIG["nparse"]["rolls"])
    merged["nparse"]["rolls"].update(config.get("nparse", {}).get("rolls", {}))
    merged["nparse"]["frog_dancer"] = dict(DEFAULT_CONFIG["nparse"]["frog_dancer"])
    merged["nparse"]["frog_dancer"].update(config.get("nparse", {}).get("frog_dancer", {}))
    merged["nparse"]["ch_chain"] = dict(DEFAULT_CONFIG["nparse"]["ch_chain"])
    merged["nparse"]["ch_chain"].update(config.get("nparse", {}).get("ch_chain", {}))
    merged["nparse"]["dps"] = dict(DEFAULT_CONFIG["nparse"]["dps"])
    merged["nparse"]["dps"].update(config.get("nparse", {}).get("dps", {}))
    merged["nparse"]["aggro"] = dict(DEFAULT_CONFIG["nparse"]["aggro"])
    merged["nparse"]["aggro"].update(config.get("nparse", {}).get("aggro", {}))
    merged["nparse"]["spells"] = dict(DEFAULT_CONFIG["nparse"]["spells"])
    merged["nparse"]["spells"].update(config.get("nparse", {}).get("spells", {}))
    merged["triggers"] = config.get("triggers", DEFAULT_CONFIG["triggers"])
    return merged


def save_config(config):
    global CONFIG_VERSION
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG_PATH.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
    tmp.replace(CONFIG_PATH)
    CONFIG_VERSION += 1


CONFIG_LOCK = threading.Lock()
CONFIG = load_config()
CONFIG.setdefault("ring8_timer", dict(DEFAULT_CONFIG["ring8_timer"]))
CONFIG.setdefault("nparse", {})
CONFIG["nparse"].setdefault("nparse_spells", dict(DEFAULT_CONFIG["nparse"]["nparse_spells"]))
CONFIG["nparse"].setdefault("rolls", dict(DEFAULT_CONFIG["nparse"]["rolls"]))
CONFIG["nparse"].setdefault("frog_dancer", dict(DEFAULT_CONFIG["nparse"]["frog_dancer"]))
CONFIG["nparse"].setdefault("text_overlay", dict(DEFAULT_CONFIG["nparse"]["text_overlay"]))
CONFIG["nparse"].setdefault("ch_chain", dict(DEFAULT_CONFIG["nparse"]["ch_chain"]))
CONFIG["nparse"].setdefault("dps", dict(DEFAULT_CONFIG["nparse"]["dps"]))
CONFIG["nparse"].setdefault("aggro", dict(DEFAULT_CONFIG["nparse"]["aggro"]))
save_config(CONFIG)


def run_audio_command(command):
    try:
        return subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError as exc:
        broadcast("error", {"message": f"Audio command failed: {exc}"})
        return None


def speak_text(text):
    text = str(text or "").strip()
    if text:
        with CONFIG_LOCK:
            voice_type = str(CONFIG.get("voice_type", "") or "").strip()
            voice_rate = int(CONFIG.get("voice_rate", 0) or 0)
            voice_pitch = int(CONFIG.get("voice_pitch", 0) or 0)
            voice_volume = max(0, min(100, int(CONFIG.get("voice_volume", 100) or 0)))
        speed = 175 + int(max(-100, min(100, voice_rate)) * 0.9)
        pitch = 50 + int(max(-100, min(100, voice_pitch)) * 0.45)
        with NamedTemporaryFile(prefix="linux-gina-voice-", suffix=".wav", delete=False) as tmp:
            voice_path = tmp.name
        try:
            subprocess.run(
                [
                    "espeak-ng",
                    "-v",
                    voice_type or "en-us",
                    "-s",
                    str(speed),
                    "-p",
                    str(max(0, min(99, pitch))),
                    "-w",
                    voice_path,
                    text,
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True,
            )
            subprocess.Popen(
                [
                    "/bin/sh",
                    "-c",
                    "paplay --volume=\"$2\" \"$1\"; rm -f \"$1\"",
                    "linux-gina-voice",
                    voice_path,
                    str(round(65536 * voice_volume / 100)),
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except (OSError, subprocess.CalledProcessError) as exc:
            try:
                Path(voice_path).unlink(missing_ok=True)
            except OSError:
                pass
            broadcast("error", {"message": f"Voice playback failed: {exc}"})


def xmi_vlq(data, offset):
    value = 0
    while offset < len(data):
        byte = data[offset]
        offset += 1
        value = (value << 7) | (byte & 0x7f)
        if byte < 0x80:
            break
    return value, offset


def xmi_note_events(data):
    offset = 0
    clock = 0
    notes = []
    while offset < len(data):
        while offset < len(data) and data[offset] < 0x80:
            clock += data[offset]
            offset += 1
        if offset >= len(data):
            break
        status = data[offset]
        offset += 1
        if status == 0xff:
            if offset >= len(data):
                break
            offset += 1
            length, offset = xmi_vlq(data, offset)
            offset += length
            continue
        if status in (0xf0, 0xf7):
            length, offset = xmi_vlq(data, offset)
            offset += length
            continue
        kind = status & 0xf0
        channel = status & 0x0f
        if kind == 0x90:
            if offset + 2 > len(data):
                break
            note, velocity = data[offset:offset + 2]
            offset += 2
            _duration, offset = xmi_vlq(data, offset)
            if velocity and channel != 9:
                notes.append((clock, int(note), channel))
        elif kind in (0x80, 0xa0, 0xb0, 0xe0):
            offset += 2
        elif kind in (0xc0, 0xd0):
            offset += 1
        else:
            break
    return notes


def normalize_beep_notes(notes):
    # Preserve the source octave so wide-ranging themes such as the Final
    # Fantasy Prelude retain their recognizable high notes. The synthesizer's
    # supported MIDI range is the only clipping applied.
    return [max(24, min(108, int(note))) for note in notes] or [81]


def load_kelethin_beep_notes():
    candidates = [
        Path.home() / "Games" / "EverQuest" / "gfaydark.xmi",
        Path.home() / "Games" / "Zoic-P99-Client" / "gfaydark.xmi",
        Path.home() / "Games" / "EverQuest-Basic" / "gfaydark.xmi",
    ]
    for path in candidates:
        if not path.is_file():
            continue
        try:
            source = path.read_bytes()
            tracks = []
            offset = 0
            while True:
                marker = source.find(b"EVNT", offset)
                if marker < 0 or marker + 8 > len(source):
                    break
                length = int.from_bytes(source[marker + 4:marker + 8], "big")
                events = xmi_note_events(source[marker + 8:marker + 8 + length])
                if 16 <= len(events) <= 300:
                    tracks.append(events)
                offset = marker + 8 + length
            if not tracks:
                continue
            # The sparsest form contains the clean Kelethin arrangement. Keep
            # its sustained melodic voices while leaving out the bass line and
            # very short decorative channel.
            arrangement = min(tracks, key=len)
            channels = {}
            for event in arrangement:
                channels.setdefault(event[2], []).append(event)
            featured_channels = {
                channel
                for channel, events in channels.items()
                if len(events) >= 12
                and sum(event[1] for event in events) / len(events) >= 55
            }
            featured = [
                event for event in arrangement if event[2] in featured_channels
            ]
            if featured:
                return normalize_beep_notes([note for _clock, note, _channel in featured])
        except (OSError, ValueError):
            continue
    return [81]


def midi_note_tracks(path):
    source = path.read_bytes()
    if len(source) < 14 or source[:4] != b"MThd":
        raise ValueError("Not a standard MIDI file")
    header_length = int.from_bytes(source[4:8], "big")
    offset = 8 + header_length
    tracks = []
    while offset + 8 <= len(source):
        marker = source[offset:offset + 4]
        length = int.from_bytes(source[offset + 4:offset + 8], "big")
        data = source[offset + 8:offset + 8 + length]
        offset += 8 + length
        if marker != b"MTrk":
            continue
        cursor = 0
        clock = 0
        running_status = None
        notes = []
        while cursor < len(data):
            delta, cursor = xmi_vlq(data, cursor)
            clock += delta
            if cursor >= len(data):
                break
            if data[cursor] < 0x80:
                if running_status is None:
                    break
                status = running_status
            else:
                status = data[cursor]
                cursor += 1
                if status < 0xf0:
                    running_status = status
            if status == 0xff:
                if cursor >= len(data):
                    break
                cursor += 1
                length, cursor = xmi_vlq(data, cursor)
                cursor += length
                continue
            if status in (0xf0, 0xf7):
                length, cursor = xmi_vlq(data, cursor)
                cursor += length
                continue
            kind = status & 0xf0
            channel = status & 0x0f
            if kind in (0xc0, 0xd0):
                cursor += 1
                continue
            if cursor + 2 > len(data):
                break
            note, velocity = data[cursor:cursor + 2]
            cursor += 2
            if kind == 0x90 and velocity and channel != 9:
                notes.append((clock, int(note)))
        tracks.append(notes)
    return tracks


def midi_timing(path):
    source = path.read_bytes()
    if len(source) < 14 or source[:4] != b"MThd":
        raise ValueError("Not a standard MIDI file")
    division = int.from_bytes(source[12:14], "big")
    if not division or division & 0x8000:
        raise ValueError("SMPTE MIDI timing is not supported")
    header_length = int.from_bytes(source[4:8], "big")
    offset = 8 + header_length
    tempos = []
    signatures = []
    while offset + 8 <= len(source):
        marker = source[offset:offset + 4]
        length = int.from_bytes(source[offset + 4:offset + 8], "big")
        data = source[offset + 8:offset + 8 + length]
        offset += 8 + length
        if marker != b"MTrk":
            continue
        cursor = 0
        clock = 0
        running_status = None
        while cursor < len(data):
            delta, cursor = xmi_vlq(data, cursor)
            clock += delta
            if cursor >= len(data):
                break
            if data[cursor] < 0x80:
                if running_status is None:
                    break
                status = running_status
            else:
                status = data[cursor]
                cursor += 1
                if status < 0xf0:
                    running_status = status
            if status == 0xff:
                if cursor >= len(data):
                    break
                meta_type = data[cursor]
                cursor += 1
                meta_length, cursor = xmi_vlq(data, cursor)
                payload = data[cursor:cursor + meta_length]
                cursor += meta_length
                if meta_type == 0x51 and len(payload) == 3:
                    tempos.append((clock, int.from_bytes(payload, "big")))
                elif meta_type == 0x58 and len(payload) >= 2:
                    signatures.append((clock, int(payload[0]), 2 ** int(payload[1])))
                continue
            if status in (0xf0, 0xf7):
                event_length, cursor = xmi_vlq(data, cursor)
                cursor += event_length
                continue
            cursor += 1 if status & 0xf0 in (0xc0, 0xd0) else 2
    tempos = sorted(set(tempos))
    signatures = sorted(set(signatures))
    if not tempos or tempos[0][0] > 0:
        tempos.insert(0, (0, 500000))
    if not signatures or signatures[0][0] > 0:
        signatures.insert(0, (0, 4, 4))
    return division, tempos, signatures


def midi_tick_span_seconds(start_tick, end_tick, division, tempos):
    if end_tick <= start_tick:
        return 0.0
    active_tempo = 500000
    cursor = start_tick
    seconds = 0.0
    for tick, tempo in tempos:
        if tick <= start_tick:
            active_tempo = tempo
            continue
        if tick >= end_tick:
            break
        seconds += (tick - cursor) * active_tempo / 1000000.0 / division
        cursor = tick
        active_tempo = tempo
    return seconds + (end_tick - cursor) * active_tempo / 1000000.0 / division


def load_beep_melody_measures(melody_key):
    definition = BEEP_MELODIES.get(melody_key) or BEEP_MELODIES["chrono_600ad"]
    if definition.get("format") == "xmi":
        return []
    tracks = midi_note_tracks(definition["path"])
    division, tempos, signatures = midi_timing(definition["path"])
    _signature_tick, numerator, denominator = signatures[0]
    measure_ticks = max(1, round(division * numerator * 4 / denominator))
    featured_tracks = set(definition.get("featured_tracks", ()))
    grouped = {}
    for track_index, track in enumerate(tracks):
        if featured_tracks and track_index not in featured_tracks:
            continue
        for clock, note in track:
            measure_index = int(clock // measure_ticks)
            grouped.setdefault(measure_index, []).append((clock, note))
    measures = []
    for measure_index, notes in sorted(grouped.items()):
        start_tick = measure_index * measure_ticks
        end_tick = start_tick + measure_ticks
        events = [
            (midi_tick_span_seconds(start_tick, clock, division, tempos), note)
            for clock, note in sorted(notes)
        ]
        measures.append({
            "index": measure_index,
            "events": events,
            "duration": midi_tick_span_seconds(start_tick, end_tick, division, tempos),
        })
    return measures


def next_beep_measure(melody_key, playback_mode):
    global BEEP_ACTIVE_MELODY
    with BEEP_MELODY_LOCK:
        active_selection = (melody_key, playback_mode)
        if active_selection != BEEP_ACTIVE_MELODY:
            BEEP_MEASURE_INDEXES[melody_key] = 0
            BEEP_ACTIVE_MELODY = active_selection
        if melody_key not in BEEP_MELODY_MEASURES:
            try:
                BEEP_MELODY_MEASURES[melody_key] = load_beep_melody_measures(melody_key)
            except (OSError, ValueError):
                BEEP_MELODY_MEASURES[melody_key] = []
        measures = BEEP_MELODY_MEASURES[melody_key]
        if not measures:
            return None
        index = BEEP_MEASURE_INDEXES.get(melody_key, 0) % len(measures)
        BEEP_MEASURE_INDEXES[melody_key] = (index + 1) % len(measures)
        return measures[index]


def load_beep_melody_notes(melody_key):
    definition = BEEP_MELODIES.get(melody_key) or BEEP_MELODIES["chrono_600ad"]
    if definition.get("format") == "xmi":
        return load_kelethin_beep_notes()
    try:
        tracks = midi_note_tracks(definition["path"])
        arrangement = []
        featured_tracks = set(definition.get("featured_tracks", ()))
        for track_index, track in enumerate(tracks):
            if featured_tracks and track_index not in featured_tracks:
                continue
            for event_index, (clock, note) in enumerate(track):
                arrangement.append((clock, track_index, event_index, note))
        arrangement.sort(key=lambda event: event[:3])
        if arrangement:
            return normalize_beep_notes([event[3] for event in arrangement])
    except (OSError, ValueError):
        pass
    return [81]


def next_beep_notes(count=1, playback_mode="midi"):
    global BEEP_ACTIVE_MELODY
    with CONFIG_LOCK:
        melody_key = str(CONFIG.get("beep_melody", "chrono_600ad"))
    if melody_key not in BEEP_MELODIES:
        melody_key = "chrono_600ad"
    with BEEP_MELODY_LOCK:
        active_selection = (melody_key, playback_mode)
        if active_selection != BEEP_ACTIVE_MELODY:
            BEEP_MELODY_INDEXES[melody_key] = 0
            BEEP_ACTIVE_MELODY = active_selection
        if melody_key not in BEEP_MELODY_NOTES:
            BEEP_MELODY_NOTES[melody_key] = load_beep_melody_notes(melody_key)
        notes = BEEP_MELODY_NOTES[melody_key]
        index = BEEP_MELODY_INDEXES.get(melody_key, 0)
        selected = [notes[(index + step) % len(notes)] for step in range(max(1, count))]
        BEEP_MELODY_INDEXES[melody_key] = (index + len(selected)) % len(notes)
        return selected


def ensure_beep_wav(notes=(81,), playback_mode="midi"):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    notes = tuple(max(24, min(108, int(note))) for note in notes) or (81,)
    phrase_key = "-".join(str(note) for note in notes)
    path = DATA_DIR / f"melody-{playback_mode}-centered-{phrase_key}.wav"
    if path.exists():
        return path
    sample_rate = 44100
    amplitude = 12000
    note_duration = 0.18 if playback_mode == "midi" else 0.16
    note_frames = int(sample_rate * note_duration)
    with wave.open(str(path), "wb") as wav:
        # Duplicate each sample into explicit left/right channels. This keeps
        # the alert centered even on players that do not remix mono streams.
        wav.setnchannels(2)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        for note in notes:
            frequency = 440.0 * (2.0 ** ((note - 69) / 12.0))
            for index in range(note_frames):
                progress = index / max(1, note_frames - 1)
                if playback_mode != "midi":
                    envelope = min(1.0, progress / 0.05) * ((1.0 - progress) ** 1.35)
                    phase = 2 * math.pi * frequency * index / sample_rate
                    tone = (
                        math.sin(phase)
                        + 0.32 * math.sin(phase * 2)
                        + 0.12 * math.sin(phase * 3)
                    ) / 1.44
                else:
                    envelope = min(1.0, progress / 0.08, (1.0 - progress) / 0.18)
                    phase = 2 * math.pi * frequency * index / sample_rate
                    tone = (math.sin(phase) + 0.18 * math.sin(phase * 2)) / 1.18
                sample = int(amplitude * envelope * tone)
                encoded = sample.to_bytes(2, "little", signed=True)
                wav.writeframesraw(encoded + encoded)
    return path


def ensure_rhythmic_beep_wav(melody_key, measure):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    measure_index = int(measure.get("index") or 0)
    path = DATA_DIR / f"melody-original-bar-{melody_key}-{measure_index}.wav"
    if path.exists():
        return path
    sample_rate = 44100
    duration = max(0.1, min(12.0, float(measure.get("duration") or 0.1)))
    frame_count = max(1, int(sample_rate * duration))
    samples = [0.0] * frame_count
    events = list(measure.get("events") or [])
    distinct_onsets = sorted(set(float(onset) for onset, _note in events))
    for onset, note in events:
        onset = max(0.0, float(onset))
        next_onset = next((value for value in distinct_onsets if value > onset), duration)
        note_duration = min(0.42, max(0.08, (next_onset - onset) * 0.88), duration - onset)
        start_frame = min(frame_count, max(0, int(onset * sample_rate)))
        note_frames = max(1, int(note_duration * sample_rate))
        frequency = 440.0 * (2.0 ** ((max(24, min(108, int(note))) - 69) / 12.0))
        for note_frame in range(min(note_frames, frame_count - start_frame)):
            progress = note_frame / max(1, note_frames - 1)
            envelope = min(1.0, progress / 0.05) * ((1.0 - progress) ** 1.35)
            phase = 2 * math.pi * frequency * note_frame / sample_rate
            tone = (math.sin(phase) + 0.32 * math.sin(phase * 2) + 0.12 * math.sin(phase * 3)) / 1.44
            samples[start_frame + note_frame] += 7600 * envelope * tone
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(2)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        encoded = bytearray()
        for sample in samples:
            value = max(-32768, min(32767, int(sample)))
            frame = value.to_bytes(2, "little", signed=True)
            encoded.extend(frame + frame)
        wav.writeframes(encoded)
    return path


def play_queued_beep(request):
    global BEEP_PLAYBACK_PROCESS
    beep_volume, playback_mode, melody_key = request
    with BEEP_PLAYBACK_LOCK:
        measure = next_beep_measure(melody_key, playback_mode) if playback_mode == "original_bar" else None
        if measure:
            notes = [note for _onset, note in measure["events"]]
            wav_path = ensure_rhythmic_beep_wav(melody_key, measure)
            beat_offsets = sorted(set(onset for onset, _note in measure["events"]))
            phrase_duration = float(measure["duration"])
        else:
            note_count = BEEP_PLAYBACK_NOTE_COUNTS[playback_mode] or 8
            notes = next_beep_notes(note_count, playback_mode)
            wav_path = ensure_beep_wav(notes, playback_mode)
            beat_offsets = []
            phrase_duration = (0.18 if playback_mode == "midi" else 0.16) * len(notes)
        BEEP_PLAYBACK_PROCESS = run_audio_command([
            "paplay",
            f"--volume={round(65536 * beep_volume / 100)}",
            str(wav_path),
        ])
        if BEEP_PLAYBACK_PROCESS is not None:
            FROG_BEAT_EVENTS.put({
                "started_at": time.time(),
                "playback_mode": playback_mode,
                "beat_seconds": 0.18 if playback_mode == "midi" else 0.16,
                "beat_count": len(notes),
                "beat_offsets": beat_offsets,
                "phrase_duration": phrase_duration,
            })
        process = BEEP_PLAYBACK_PROCESS
    if process is None:
        return False
    try:
        process.wait()
    except (AttributeError, OSError):
        while process.poll() is None:
            time.sleep(0.02)
    with BEEP_PLAYBACK_LOCK:
        if BEEP_PLAYBACK_PROCESS is process:
            BEEP_PLAYBACK_PROCESS = None
    return True


def beep_audio_worker():
    global BEEP_AUDIO_WORKER
    while True:
        with BEEP_WORKER_LOCK:
            try:
                request = BEEP_AUDIO_QUEUE.get_nowait()
            except queue.Empty:
                BEEP_AUDIO_WORKER = None
                return
        try:
            play_queued_beep(request)
        finally:
            BEEP_AUDIO_QUEUE.task_done()


def beep_audio():
    global BEEP_AUDIO_WORKER
    with CONFIG_LOCK:
        beep_volume = max(0, min(100, int(CONFIG.get("beep_volume", 100) or 0)))
        playback_mode = str(CONFIG.get("beep_playback", "midi"))
        melody_key = str(CONFIG.get("beep_melody", "chrono_600ad"))
    if playback_mode not in BEEP_PLAYBACK_NOTE_COUNTS:
        playback_mode = "midi"
    if melody_key not in BEEP_MELODIES:
        melody_key = "chrono_600ad"
    try:
        BEEP_AUDIO_QUEUE.put_nowait((beep_volume, playback_mode, melody_key))
    except queue.Full:
        return False
    with BEEP_WORKER_LOCK:
        if BEEP_AUDIO_WORKER is None or not BEEP_AUDIO_WORKER.is_alive():
            BEEP_AUDIO_WORKER = threading.Thread(target=beep_audio_worker, daemon=True)
            BEEP_AUDIO_WORKER.start()
    return True


def play_trigger_audio(hit):
    with CONFIG_LOCK:
        speak_enabled = bool(CONFIG.get("speak", True))
        beep_enabled = bool(CONFIG.get("beep", True))
    if speak_enabled:
        speak_text(hit.get("voice_message") or hit.get("message", ""))
    if beep_enabled:
        beep_audio()


def normalize_timer_key(value):
    return re.sub(r"\s+", " ", str(value or "").strip()).lower()


def timer_action(hit):
    return normalize_timer_key(hit.get("timer_action") or "start") or "start"


def timer_target(hit):
    return str(hit.get("timer_target") or hit.get("timer_name") or hit.get("name") or hit.get("message") or "").strip()


def remove_matching_timers(timers, hit):
    if timer_action(hit) != "stop":
        return timers
    target = normalize_timer_key(timer_target(hit))
    trigger_id = normalize_timer_key(hit.get("trigger_id"))
    if not target and not trigger_id:
        return timers
    remaining = []
    for timer in timers:
        timer_keys = {
            normalize_timer_key(timer.get("spell_id")),
            normalize_timer_key(timer.get("id")),
            normalize_timer_key(timer.get("trigger_id")),
            normalize_timer_key(timer.get("timer_name")),
            normalize_timer_key(timer.get("name")),
            normalize_timer_key(timer.get("message")),
        }
        if trigger_id and normalize_timer_key(timer.get("trigger_id")) == trigger_id:
            continue
        if target and target in timer_keys:
            continue
        remaining.append(timer)
    return remaining


def broadcast(kind, payload):
    payload = {"kind": kind, "payload": payload, "time": time.time()}
    EVENTS.put(payload)
    if kind == "trigger":
        GINA_OVERLAY_EVENTS.put(payload["payload"])
        TEXT_OVERLAY_EVENTS.put(payload["payload"])
        NPARSE_SPELLS_EVENTS.put(payload["payload"])
    elif kind == "ch_chain":
        CH_CHAIN_EVENTS.put(payload["payload"])
    elif kind == "dps":
        DPS_EVENTS.put(payload["payload"])
    elif kind == "aggro":
        AGGRO_EVENTS.put(payload["payload"])
    elif kind == "roll":
        ROLL_OVERLAY_EVENTS.put(payload["payload"])


def schedule_trigger_reminder(hit):
    delay = float(hit.get("reminder_after_seconds") or 0)
    message = str(hit.get("reminder_message") or "").strip()
    if delay <= 0 or not message:
        return

    trigger_id = str(hit.get("trigger_id") or hit.get("name") or "trigger").strip()
    reminder_key_source = hit.get("id") if hit.get("stack_timers", False) else trigger_id
    reminder_key = normalize_timer_key(reminder_key_source)

    def fire_reminder():
        with TRIGGER_REMINDER_LOCK:
            if TRIGGER_REMINDERS.get(reminder_key) is not timer:
                return
            TRIGGER_REMINDERS.pop(reminder_key, None)
        if not STATE.get("running", False):
            return
        reminder_hit = {
            "id": str(uuid.uuid4()),
            "trigger_id": f"{trigger_id}-reminder-{hit.get('id', '')}",
            "name": hit.get("reminder_name") or "Timer reminder",
            "message": message,
            "display_message": hit.get("reminder_display_message") or message,
            "use_text": True,
            "use_voice": False,
            "timer_name": "",
            "timer_seconds": 0,
            "line": hit.get("line", ""),
            "raw_line": hit.get("raw_line", ""),
            "color": hit.get("reminder_color") or hit.get("color", "#60a5fa"),
        }
        broadcast("trigger", reminder_hit)

    timer = threading.Timer(delay, fire_reminder)
    timer.daemon = True
    with TRIGGER_REMINDER_LOCK:
        previous = TRIGGER_REMINDERS.get(reminder_key)
        if previous is not None:
            previous.cancel()
        TRIGGER_REMINDERS[reminder_key] = timer
    timer.start()


def candidate_log_dirs(log_dir):
    dirs = []
    if log_dir:
        dirs.append(Path(log_dir).expanduser())
    dirs.extend(EQ_LOG_DIRS)

    result = []
    seen = set()
    for path in dirs:
        try:
            resolved = path.resolve()
        except OSError:
            resolved = path
        key = str(resolved)
        if key in seen or not path.is_dir():
            continue
        seen.add(key)
        result.append(path)
    return result


def latest_log(log_dir):
    logs = []
    for path in candidate_log_dirs(log_dir):
        logs.extend(path.glob("eqlog_*.txt"))
    logs = sorted(logs, key=lambda p: p.stat().st_mtime, reverse=True)
    return str(logs[0]) if logs else ""


def read_log_tail(path, max_bytes=65536):
    try:
        size = path.stat().st_size
        with path.open("rb") as f:
            if size > max_bytes:
                f.seek(size - max_bytes)
            data = f.read()
    except OSError:
        return ""
    return data.decode("utf-8", errors="replace")


def last_zone_event_from_log(path, chunk_size=65536):
    log_path = Path(path)
    if not log_path.is_file():
        return "", 0
    try:
        with log_path.open("rb") as handle:
            position = handle.seek(0, os.SEEK_END)
            partial = b""
            while position > 0:
                read_size = min(chunk_size, position)
                position -= read_size
                handle.seek(position)
                data = handle.read(read_size) + partial
                lines = data.split(b"\n")
                if position > 0:
                    partial = lines.pop(0)
                else:
                    partial = b""
                for raw in reversed(lines):
                    line = raw.decode("utf-8", errors="replace").rstrip("\r")
                    zone = zone_from_line(line)
                    if zone:
                        return zone, log_timestamp_from_line(line)
    except OSError:
        pass
    return "", 0


def last_zone_from_log(path):
    return last_zone_event_from_log(path)[0]


def last_zone_seen_from_log(path):
    return last_zone_event_from_log(path)[1]


def list_logs(log_dir):
    logs = []
    seen = set()
    for path in candidate_log_dirs(log_dir):
        for item in path.glob("eqlog_*.txt"):
            key = str(item)
            if key in seen:
                continue
            seen.add(key)
            logs.append(item)

    rows_by_character = {}
    for item in logs:
        last_zone, last_seen = last_zone_event_from_log(item)
        row = {
            "path": str(item),
            "name": item.name,
            "character": character_from_log_path(item),
            "last_zone": last_zone,
            "last_seen": last_seen,
            "mtime": item.stat().st_mtime,
            "size": item.stat().st_size,
            "active": str(item) == STATE.get("active_log", ""),
        }
        character_key = row["character"].strip().lower() or item.stem.lower()
        existing = rows_by_character.get(character_key)
        row_latest = (row["last_seen"] or 0, row["mtime"] or 0)
        existing_latest = ((existing or {}).get("last_seen") or 0, (existing or {}).get("mtime") or 0)
        if existing is None or row_latest > existing_latest:
            rows_by_character[character_key] = row

    return sorted(
        rows_by_character.values(),
        key=lambda row: (row["last_seen"] or 0, row["mtime"] or 0),
        reverse=True,
    )


def load_spell_catalog():
    try:
        with SPELL_CATALOG_PATH.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {"generated_at": "", "source": "", "classes": {}}
    if not isinstance(payload.get("classes"), dict):
        payload["classes"] = {}
    return payload


def spellbook_character_from_path(path):
    stem = Path(path).stem
    match = re.match(r"(?P<character>.+?)[-_ ]spellbook(?:[-_ ].*)?$", stem, re.IGNORECASE)
    return match.group("character") if match else ""


def discover_spellbook_files(log_dir=""):
    roots = []
    seen_roots = set()
    for logs in candidate_log_dirs(log_dir):
        for root in (logs, logs.parent):
            try:
                key = str(root.resolve())
            except OSError:
                key = str(root)
            if key not in seen_roots and root.is_dir():
                seen_roots.add(key)
                roots.append(root)

    files = []
    seen_files = set()
    for root in roots:
        try:
            entries = list(root.iterdir())
        except OSError:
            continue
        for path in entries:
            if not path.is_file() or path.suffix.lower() not in {".txt", ".tsv", ".csv"}:
                continue
            if "spellbook" not in path.name.lower():
                continue
            try:
                resolved = str(path.resolve())
                stat = path.stat()
            except OSError:
                continue
            if resolved in seen_files or stat.st_size > 5 * 1024 * 1024:
                continue
            seen_files.add(resolved)
            files.append({
                "path": str(path),
                "name": path.name,
                "character": spellbook_character_from_path(path),
                "mtime": stat.st_mtime,
                "size": stat.st_size,
            })
    return sorted(files, key=lambda row: row["mtime"], reverse=True)


def inventory_character_from_path(path):
    stem = Path(path).stem
    match = re.match(r"(?P<character>.+?)[-_ ]inventory$", stem, re.IGNORECASE)
    return match.group("character") if match else stem


def discover_inventory_files(log_dir=""):
    """Find EverQuest /outputfile inventory exports beside known Logs folders."""
    roots = []
    seen_roots = set()
    for logs in candidate_log_dirs(log_dir):
        root = logs.parent
        try:
            key = str(root.resolve())
        except OSError:
            key = str(root)
        if key not in seen_roots and root.is_dir():
            seen_roots.add(key)
            roots.append(root)

    files = []
    seen_files = set()
    for root in roots:
        try:
            entries = list(root.iterdir())
        except OSError:
            continue
        for path in entries:
            if not path.is_file() or not re.search(r"[-_ ]inventory\.txt$", path.name, re.IGNORECASE):
                continue
            try:
                resolved = str(path.resolve())
                stat = path.stat()
            except OSError:
                continue
            if resolved in seen_files or stat.st_size > 5 * 1024 * 1024:
                continue
            seen_files.add(resolved)
            files.append({
                "path": str(path),
                "name": path.name,
                "directory": str(root),
                "character": inventory_character_from_path(path),
                "mtime": stat.st_mtime,
                "size": stat.st_size,
            })
    return sorted(files, key=lambda row: row["mtime"], reverse=True)


def normalized_inventory_item_name(value):
    return re.sub(r"\s+", " ", str(value or "").strip().replace("’", "'").replace("`", "'").lower())


def read_inventory_export(file_row):
    try:
        lines = Path(file_row["path"]).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    if not lines:
        return []
    columns = [field.strip() for field in lines[0].split("\t")]
    column_lookup = {name.lower(): index for index, name in enumerate(columns)}
    items = []
    for raw_line in lines[1:]:
        if not raw_line.strip():
            continue
        fields = raw_line.split("\t")
        def field(name):
            index = column_lookup.get(name)
            return fields[index].strip() if index is not None and index < len(fields) else ""
        name = field("name")
        normalized_name = normalized_inventory_item_name(name)
        if not normalized_name or normalized_name == "empty":
            continue
        items.append({
            "character": file_row["character"],
            "location": field("location"),
            "name": name,
            "id": field("id"),
            "count": field("count"),
            "slots": field("slots"),
            "raid_kit": normalized_name in COMMON_RAID_KIT_ITEMS,
        })
    return items


def inventory_payload():
    with CONFIG_LOCK:
        log_dir = CONFIG.get("log_dir", "")
    files = discover_inventory_files(log_dir)
    latest_by_character = {}
    for file_row in files:
        key = file_row["character"].strip().lower()
        if key and key not in latest_by_character:
            latest_by_character[key] = file_row
    inventories = list(latest_by_character.values())
    items = []
    for file_row in inventories:
        items.extend(read_inventory_export(file_row))
    return {
        "files": files,
        "inventories": inventories,
        "items": items,
        "raid_kit_names": sorted(COMMON_RAID_KIT_ITEMS),
    }


def spellbook_discovery_payload():
    with CONFIG_LOCK:
        log_dir = CONFIG.get("log_dir", "")
    logs = list_logs(log_dir)
    return {
        "files": discover_spellbook_files(log_dir),
        "characters": [row["character"] for row in logs if row.get("character")],
        "active_character": STATE.get("character", ""),
        "active_log": STATE.get("active_log", ""),
        "classes": sorted(load_spell_catalog().get("classes", {}).keys()),
    }


def normalized_spell_name(value):
    normalized = re.sub(
        r"\s+",
        " ",
        str(value or "").strip().replace("’", "'").replace("`", "'").lower(),
    )
    return SPELLBOOK_NAME_ALIASES.get(normalized, normalized)


def spell_catalog_name_lookup(catalog):
    lookup = {}
    for class_data in catalog.get("classes", {}).values():
        for names in class_data.get("levels", {}).values():
            for name in names:
                lookup.setdefault(normalized_spell_name(name), name)
    return lookup


def parse_spellbook_export(path, catalog):
    try:
        if path.stat().st_size > 5 * 1024 * 1024:
            raise ValueError("Spellbook export is larger than 5 MB")
        text = path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError as exc:
        raise ValueError(f"Could not read spellbook export: {exc}") from exc

    lookup = spell_catalog_name_lookup(catalog)
    owned = set()
    unmatched = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        candidates = [line]
        candidates.extend(piece.strip() for piece in re.split(r"[\t^|]", line) if piece.strip())
        candidates.extend(
            re.sub(r"^(?:(?:book\s+)?slot\s*)?\d+\s*[:.)\-–—,]\s*", "", piece, flags=re.IGNORECASE)
            for piece in list(candidates)
        )
        matched = False
        for candidate in candidates:
            canonical = lookup.get(normalized_spell_name(candidate.strip('"')))
            if canonical:
                owned.add(canonical)
                matched = True
        if not matched and len(unmatched) < 8:
            unmatched.append(line[:160])
    return owned, unmatched


def find_character_log(character, log_dir=""):
    wanted = normalized_spell_name(character)
    choices = []
    for directory in candidate_log_dirs(log_dir):
        for path in directory.glob("eqlog_*.txt"):
            if normalized_spell_name(character_from_log_path(path)) == wanted:
                try:
                    choices.append(path)
                except OSError:
                    pass
    return max(choices, key=lambda path: path.stat().st_mtime) if choices else None


def latest_character_level(path, chunk_size=65536):
    if not path or not Path(path).is_file():
        return 0
    path = Path(path)
    try:
        with path.open("rb") as handle:
            position = handle.seek(0, os.SEEK_END)
            partial = b""
            while position > 0:
                read_size = min(chunk_size, position)
                position -= read_size
                handle.seek(position)
                data = handle.read(read_size) + partial
                lines = data.split(b"\n")
                partial = lines.pop(0) if position > 0 else b""
                for raw in reversed(lines):
                    match = LEVEL_GAIN_RE.search(raw.decode("utf-8", errors="replace"))
                    if match:
                        return int(match.group("level"))
    except OSError:
        return 0
    return 0


def inferred_spell_class(owned, classes):
    owned_keys = {normalized_spell_name(name) for name in owned}
    ranked = []
    for class_name, class_data in classes.items():
        names = {
            normalized_spell_name(name)
            for spells in class_data.get("levels", {}).values()
            for name in spells
        }
        matches = len(owned_keys & names)
        ranked.append((matches, matches / max(1, len(owned_keys)), class_name))
    ranked.sort(reverse=True)
    return ranked[0][2] if ranked and ranked[0][0] else ""


def spellbook_comparison(path_text="", character="", class_name="", level=0):
    catalog = load_spell_catalog()
    classes = catalog.get("classes", {})
    discovery = spellbook_discovery_payload()
    character = str(character or discovery.get("active_character") or "").strip()
    path_text = str(path_text or "").strip()
    if not path_text:
        matching = [
            row for row in discovery["files"]
            if not character or normalized_spell_name(row.get("character")) == normalized_spell_name(character)
        ]
        if matching:
            path_text = matching[0]["path"]
    if not path_text:
        return {
            **discovery,
            "ready": False,
            "character": character,
            "message": "No spellbook export found. Run /outputfile spellbook in EverQuest, then refresh.",
            "catalog_generated_at": catalog.get("generated_at", ""),
        }

    path = Path(path_text).expanduser()
    if not path.is_absolute():
        with CONFIG_LOCK:
            path = Path(CONFIG.get("log_dir", "")).parent / path
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise ValueError(f"Spellbook export not found: {path}") from exc
    if resolved.suffix.lower() not in {".txt", ".tsv", ".csv"}:
        raise ValueError("Spellbook export must be a text, TSV, or CSV file")

    owned, unmatched = parse_spellbook_export(resolved, catalog)
    if not character:
        character = spellbook_character_from_path(resolved)
    selected_class = str(class_name or "").strip()
    if selected_class not in classes:
        selected_class = inferred_spell_class(owned, classes)
    if not selected_class:
        return {
            **discovery,
            "ready": False,
            "character": character,
            "path": str(resolved),
            "message": "No wiki spell names were recognized. Check that this is an /outputfile spellbook export.",
            "unmatched_lines": unmatched,
        }

    class_data = classes[selected_class]
    class_names = {
        normalized_spell_name(name): name
        for spells in class_data.get("levels", {}).values()
        for name in spells
    }
    owned_keys = {normalized_spell_name(name) for name in owned}
    owned_class = {class_names[key] for key in class_names if key in owned_keys}
    with CONFIG_LOCK:
        log_dir = CONFIG.get("log_dir", "")
    character_log = find_character_log(character, log_dir) if character else None
    detected_level = latest_character_level(character_log)
    requested_level = max(0, min(60, int(level or 0)))
    if requested_level:
        character_level = requested_level
        level_source = "manual"
    elif detected_level:
        character_level = detected_level
        level_source = "log"
    else:
        owned_levels = [
            int(spell_level)
            for spell_level, names in class_data.get("levels", {}).items()
            if any(name in owned_class for name in names)
        ]
        character_level = max(owned_levels, default=0)
        level_source = "spellbook" if character_level else "unknown"

    rows = []
    for spell_level, names in sorted(class_data.get("levels", {}).items(), key=lambda item: int(item[0])):
        spell_level_number = int(spell_level)
        if character_level and spell_level_number > character_level:
            continue
        present = [name for name in names if name in owned_class]
        missing = [name for name in names if name not in owned_class]
        rows.append({
            "level": spell_level_number,
            "owned": present,
            "missing": missing,
            "total": len(names),
            "complete": not missing,
            "wiki_url": f"{class_data.get('wiki_url', '')}#Level_{spell_level_number}",
        })

    eligible_total = sum(row["total"] for row in rows)
    eligible_owned = sum(len(row["owned"]) for row in rows)
    return {
        **discovery,
        "ready": True,
        "path": str(resolved),
        "character": character,
        "class_name": selected_class,
        "character_level": character_level,
        "level_source": level_source,
        "character_log": str(character_log or ""),
        "owned_count": eligible_owned,
        "missing_count": eligible_total - eligible_owned,
        "eligible_total": eligible_total,
        "recognized_count": len(owned),
        "levels": rows,
        "wiki_url": class_data.get("wiki_url", ""),
        "catalog_generated_at": catalog.get("generated_at", ""),
        "unmatched_lines": unmatched,
    }


def discover_gina_packages():
    packages = []
    seen = set()
    for directory in DEFAULT_GINA_IMPORT_DIRS:
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.gtp")):
            if path in seen:
                continue
            seen.add(path)
            packages.append({
                "path": str(path),
                "name": path.name,
                "size": path.stat().st_size,
                "mtime": path.stat().st_mtime,
            })
    return packages


def normalize_nparse_key(value):
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


TRIGGER_TYPE_COLORS = {
    "buff": "#22c55e",
    "debuff": "#c084fc",
    "mob_timer": "#f59e0b",
    "raid_danger": "#ef4444",
    "heal": "#2dd4bf",
    "discipline": "#3b82f6",
    "notification": "#facc15",
    "spell": "#38bdf8",
}


def trigger_palette_color(trigger, fallback="#60a5fa"):
    """Choose a stable color from GINA category/group metadata."""
    def label(value):
        return " ".join(re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).split())

    category = label(trigger.get("category"))
    group = label(trigger.get("group"))
    name = label(trigger.get("name"))
    pattern = str(trigger.get("pattern") or "").lower()
    metadata = " ".join((category, group, name))

    if ("slain" in pattern or "quillmane" in group
            or ("plane of sky" in group and category == "timers")
            or ("mobs" in group and int(trigger.get("timer_seconds") or 0) > 0)):
        return TRIGGER_TYPE_COLORS["mob_timer"]
    if any(word in metadata for word in ("debuff", " dot", "slow", "mez", "root break")):
        return TRIGGER_TYPE_COLORS["debuff"]
    if any(word in metadata for word in ("aoe", "death touch", "raid mob spell")):
        return TRIGGER_TYPE_COLORS["raid_danger"]
    if "buff" in metadata:
        return TRIGGER_TYPE_COLORS["buff"]
    if "heal" in metadata:
        return TRIGGER_TYPE_COLORS["heal"]
    if "discipline" in metadata or category == "skills":
        return TRIGGER_TYPE_COLORS["discipline"]
    if category == "timers" or int(trigger.get("timer_seconds") or 0) > 0:
        return TRIGGER_TYPE_COLORS["mob_timer"]
    if "notification" in category:
        return TRIGGER_TYPE_COLORS["notification"]
    if category == "spells":
        return TRIGGER_TYPE_COLORS["spell"]
    return fallback


def normalize_imported_trigger(trigger):
    """Keep imported actor/target alerts explicit and readable."""
    normalized = dict(trigger)
    name_key = normalize_nparse_key(normalized.get("name"))
    if name_key == "hailcorpse":
        normalized.update({
            "pattern": r"^(?P<by>[^ ]+) says, 'Hail, (?P<target>[^']+)'s corpse'$",
            "message": "${by} hailed ${target}'s corpse",
            "display_text": "${by} hailed ${target}'s corpse",
            "voice_text": "${target} needs a rez",
            "use_text": True,
        })
    elif name_key in {"hailme", "hailreceived"}:
        normalized.update({
            "pattern": r"^(?P<by>[^ ]+) says, 'Hail, (?P<target>.+?)\s*'$",
            "message": "${by} hailed ${target}",
            "display_text": "${by} hailed ${target}",
            "use_text": True,
        })
        if normalized.get("use_voice", False):
            normalized["voice_text"] = "${by} hailed ${target}"
    elif name_key == "fte":
        normalized.update({
            "pattern": r"^(?P<mob>.+?) engages (?P<player>[^!]+)!$",
            "message": "FTE: ${player} on ${mob}",
            "display_text": "FTE: ${player} on ${mob}",
            "voice_text": "${player} got first engage on ${mob}",
            "use_text": True,
        })
    elif "death touches" in str(normalized.get("group") or "").lower():
        death_touch_patterns = {
            "dread": r"^(?P<mob>Dread) shouts '(?P<target>[A-Z]{4,})'$",
            "fright": r"^(?P<mob>Fright) shouts '(?P<target>[A-Z]{4,})'$",
            "masteryael": r"^(?P<mob>Master Yael) shouts '(?P<target>[A-Z]{4,})'$",
            "planeofskydtmobs": (
                r"^(?P<mob>Sister of the Spire|The Spiroc Lord|Bazzt Zzzt|Eye of Veeshan|"
                r"Keeper of Souls|Overseer of Air|the Hand of Veeshan|a greater sphinx|Key Master) "
                r"shouts '(?P<target>[A-Z]{4,})'$"
            ),
        }
        pattern = death_touch_patterns.get(name_key)
        if pattern:
            normalized.update({
                "pattern": pattern,
                "message": "DEATH TOUCH: ${target} — ${mob}",
                "display_text": "DEATH TOUCH: ${target} — ${mob}",
                "voice_text": "${target} took ${mob}'s death touch",
                "use_text": True,
                "use_voice": True,
            })
    return normalized


def apply_trigger_palette_migration():
    """Recolor only untouched default-blue triggers, once."""
    with CONFIG_LOCK:
        if int(CONFIG.get("trigger_palette_version") or 0) >= 1:
            return
        triggers = []
        for stored in CONFIG.get("triggers", []):
            trigger = normalize_imported_trigger(stored)
            if str(trigger.get("color") or "#60a5fa").lower() == "#60a5fa":
                trigger["color"] = trigger_palette_color(trigger)
            triggers.append(trigger)
        CONFIG["triggers"] = triggers
        CONFIG["trigger_palette_version"] = 1
        save_config(CONFIG)


apply_trigger_palette_migration()


def map_file_key(path):
    stem = path.stem.lower()
    return re.sub(r"_\d+$", "", stem)


def parse_nparse_alias_file(path, alias_to_key, label_by_key):
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        left, right = [part.strip() for part in line.split("=", 1)]
        if not left or not right:
            continue
        alias_to_key[normalize_nparse_key(left)] = right
        alias_to_key[normalize_nparse_key(right)] = right
        label_by_key.setdefault(right, left)


def parse_nparse_map_file(path):
    lines = []
    points = []
    min_x = min_y = float("inf")
    max_x = max_y = float("-inf")

    def include_xy(x, y):
        nonlocal min_x, min_y, max_x, max_y
        min_x = min(min_x, x)
        min_y = min(min_y, y)
        max_x = max(max_x, x)
        max_y = max(max_y, y)

    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("L "):
            parts = [part.strip() for part in line[2:].split(",")]
            if len(parts) < 9:
                continue
            try:
                x1, y1, z1, x2, y2, z2 = [float(part) for part in parts[:6]]
                color = [int(float(part)) for part in parts[6:9]]
            except ValueError:
                continue
            lines.append({
                "x1": x1,
                "y1": y1,
                "z1": z1,
                "x2": x2,
                "y2": y2,
                "z2": z2,
                "color": color,
            })
            include_xy(x1, y1)
            include_xy(x2, y2)
        elif line.startswith("P "):
            parts = [part.strip() for part in line[2:].split(",")]
            if len(parts) < 8:
                continue
            try:
                x, y, z = [float(part) for part in parts[:3]]
                color = [int(float(part)) for part in parts[3:6]]
                size = int(float(parts[6]))
            except ValueError:
                continue
            label = ",".join(parts[7:]).strip().replace("_", " ")
            points.append({
                "x": x,
                "y": y,
                "z": z,
                "color": color,
                "size": size,
                "label": label,
            })
            include_xy(x, y)

    if not lines and not points:
        min_x = min_y = 0.0
        max_x = max_y = 1.0
    elif min_x == float("inf"):
        min_x = min_y = 0.0
        max_x = max_y = 1.0

    return {
        "lines": lines,
        "points": points,
        "bounds": {
            "min_x": min_x,
            "min_y": min_y,
            "max_x": max_x,
            "max_y": max_y,
        },
    }


def load_nparse_assets():
    alias_to_key = {}
    label_by_key = {}
    parse_nparse_alias_file(NPARSE_DATA_DIR / "map_keys.ini", alias_to_key, label_by_key)
    parse_nparse_alias_file(NPARSE_DATA_DIR / "map_keys_who.ini", alias_to_key, label_by_key)

    zones = {}
    zone_choices = []
    for directory in (NPARSE_DATA_DIR / "map_files", NPARSE_DATA_DIR / "classic_maps"):
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.txt")):
            key = map_file_key(path)
            parsed = parse_nparse_map_file(path)
            label = label_by_key.get(key, path.stem.replace("_", " "))
            score = len(parsed["lines"]) + len(parsed["points"])
            previous = zones.get(key)
            if previous and previous.get("score", 0) >= score:
                continue
            parsed.update({
                "key": key,
                "label": label,
                "source": str(path),
                "score": score,
            })
            zones[key] = parsed

    for key, zone in zones.items():
        zone_choices.append({"key": key, "label": zone["label"]})
    zone_choices.sort(key=lambda item: item["label"].lower())

    zone_timers = {}
    timer_path = NPARSE_DATA_DIR / "map_timers.csv"
    if timer_path.exists():
        for raw in timer_path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "," not in line:
                continue
            zone_key, duration_text = [part.strip() for part in line.split(",", 1)]
            duration_seconds = parse_timer_span(duration_text)
            zone_timers[normalize_nparse_key(zone_key)] = {
                "key": zone_key,
                "duration_text": duration_text,
                "duration_seconds": duration_seconds,
            }

    source_config = {}
    if NPARSE_CONFIG_PATH.exists():
        try:
            source_config = json.loads(NPARSE_CONFIG_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            source_config = {}
    custom_timers = source_config.get("spells", {}).get("custom_timers", []) or []
    last_zone = source_config.get("maps", {}).get("last_zone", "")
    return {
        "alias_to_key": alias_to_key,
        "label_by_key": label_by_key,
        "zones": zones,
        "zone_choices": zone_choices,
        "zone_timers": zone_timers,
        "source_config": source_config,
        "custom_timers": custom_timers,
        "last_zone": last_zone,
    }


def gina_pattern_to_python(pattern, enable_regex=True):
    if not pattern:
        return ""
    if not enable_regex:
        return re.escape(pattern)
    pattern = re.sub(r"\\\{(TS|ts|s1|s2|s|S|c|C|n)\\\}", r"{\1}", pattern)
    counters = {}

    def replace_placeholder(match):
        token = match.group(1)
        key = token.upper()
        counters[key] = counters.get(key, 0) + 1
        name = f"GINA_{key}_{counters[key]}"
        if key == "TS":
            return f"(?P<{name}>\\d+(?:\\.\\d+)?\\s*(?:ms|s|sec|secs|second|seconds|m|min|mins|minute|minutes|h|hr|hrs|hour|hours)(?:\\s+\\d+(?:\\.\\d+)?\\s*(?:ms|s|sec|secs|second|seconds|m|min|mins|minute|minutes|h|hr|hrs|hour|hours))*|\\d+(?::\\d{{1,2}}(?::\\d{{1,2}})?)?|\\d+)"
        if key == "N":
            return f"(?P<{name}>\\d+)"
        if key == "C":
            return f"(?P<{name}>[A-Za-z][A-Za-z`'-]*)"
        suffix = pattern[match.end():].strip()
        quantifier = ".+" if suffix in ("", "$") else ".+?"
        return f"(?P<{name}>{quantifier})"

    converted = re.sub(r"\{(TS|ts|s1|s2|s|S|c|C|n)\}", replace_placeholder, pattern)
    converted = re.sub(r"\(\?<([A-Za-z_]\w*)>", r"(?P<\1>", converted)
    converted = re.sub(r"\(\?'([A-Za-z_]\w*)'", r"(?P<\1>", converted)
    converted = converted.replace("(?>", "(?:")
    return converted


def parse_timer_span(value):
    if value is None:
        return 0
    text = str(value).strip()
    if not text:
        return 0
    if re.fullmatch(r"\d+(?::\d{1,2}){1,2}", text):
        parts = [int(part) for part in text.split(":")]
        if len(parts) == 2:
            return parts[0] * 60 + parts[1]
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    if re.fullmatch(r"\d+(?:\.\d+)?", text):
        return int(float(text))
    total = 0.0
    for amount, unit in re.findall(r"(\d+(?:\.\d+)?)\s*(ms|s|sec|secs|second|seconds|m|min|mins|minute|minutes|h|hr|hrs|hour|hours)", text, re.I):
        number = float(amount)
        unit = unit.lower()
        if unit == "ms":
            total += number / 1000
        elif unit.startswith("h"):
            total += number * 3600
        elif unit.startswith("m"):
            total += number * 60
        else:
            total += number
    return int(total)


NPARSE_LIBRARY = load_nparse_assets()


def seed_nparse_config_defaults():
    with CONFIG_LOCK:
        nparse = dict(CONFIG.get("nparse", DEFAULT_CONFIG["nparse"]))
        discord = dict(DEFAULT_CONFIG["nparse"]["discord"])
        discord.update(nparse.get("discord", {}))
        maps = dict(DEFAULT_CONFIG["nparse"]["maps"])
        maps.update(nparse.get("maps", {}))
        if not maps.get("selected_zone"):
            maps["selected_zone"] = NPARSE_LIBRARY.get("last_zone", "")
        text_overlay = dict(DEFAULT_CONFIG["nparse"]["text_overlay"])
        text_overlay.update(nparse.get("text_overlay", {}))
        nparse_spells = dict(DEFAULT_CONFIG["nparse"]["nparse_spells"])
        nparse_spells.update(nparse.get("nparse_spells", {}))
        rolls = dict(DEFAULT_CONFIG["nparse"]["rolls"])
        rolls.update(nparse.get("rolls", {}))
        frog_dancer = dict(DEFAULT_CONFIG["nparse"]["frog_dancer"])
        frog_dancer.update(nparse.get("frog_dancer", {}))
        ch_chain = dict(DEFAULT_CONFIG["nparse"]["ch_chain"])
        ch_chain.update(nparse.get("ch_chain", {}))
        dps = dict(DEFAULT_CONFIG["nparse"]["dps"])
        dps.update(nparse.get("dps", {}))
        aggro = dict(DEFAULT_CONFIG["nparse"]["aggro"])
        aggro.update(nparse.get("aggro", {}))
        spells = dict(DEFAULT_CONFIG["nparse"]["spells"])
        spells.update(nparse.get("spells", {}))
        if not spells.get("custom_timers"):
            spells["custom_timers"] = list(NPARSE_LIBRARY.get("custom_timers", []))
        CONFIG["nparse"] = {
            "discord": discord,
            "maps": maps,
            "text_overlay": text_overlay,
            "nparse_spells": nparse_spells,
            "rolls": rolls,
            "frog_dancer": frog_dancer,
            "ch_chain": ch_chain,
            "dps": dps,
            "aggro": aggro,
            "spells": spells,
        }


seed_nparse_config_defaults()
save_config(CONFIG)


def build_nparse_custom_triggers():
    triggers = []
    for index, entry in enumerate(NPARSE_LIBRARY.get("custom_timers", []), start=1):
        if not isinstance(entry, (list, tuple)) or len(entry) < 3:
            continue
        name = str(entry[0] or f"Timer {index}").strip() or f"Timer {index}"
        pattern_text = str(entry[1] or "").strip()
        duration_text = str(entry[2] or "").strip()
        if not pattern_text:
            continue
        pattern = gina_pattern_to_python(pattern_text, True)
        try:
            re.compile(pattern, re.IGNORECASE)
        except re.error:
            continue
        triggers.append({
            "id": f"nparse-{index}-{normalize_nparse_key(name)}",
            "name": name,
            "pattern": pattern,
            "message": name,
            "timer_name": name,
            "timer_seconds": parse_timer_span(duration_text),
            "dynamic_timer": "{TS}" in pattern_text or "{ts}" in pattern_text,
            "color": "#60a5fa",
            "enabled": True,
            "source": "nparse",
            "category": "nparse",
            "use_text": True,
            "use_voice": False,
        })
    return triggers


def expand_message(template, match, line, context=None):
    if not template:
        return ""
    context = context or {}
    values = match.groupdict() if match else {}
    message = template.replace("{l}", line.rstrip("\n"))
    if "counter" in context:
        message = message.replace("{COUNTER}", str(context["counter"]))
    if "timer_seconds" in context:
        seconds = int(context["timer_seconds"])
        message = message.replace("{TS}", str(seconds))
        message = message.replace("{ts}", str(seconds))
    if match:
        for index, value in enumerate(match.groups(), start=1):
            if value is None:
                continue
            message = message.replace("${" + str(index) + "}", value)
            message = message.replace("{" + str(index) + "}", value)
        for token in ("TS", "ts", "S", "s", "C", "c", "N", "n", "s1", "s2"):
            key = token.upper()
            value = None
            if token in ("s1", "s2"):
                value = values.get(f"GINA_{token.upper()}_1")
            elif key == "TS":
                value = values.get("GINA_TS_1")
            else:
                value = values.get(f"GINA_{key}_1")
                if value is None and key == "C":
                    value = values.get("GINA_S_1")
                if value is None and key == "S":
                    value = values.get("GINA_C_1")
            if value is not None:
                message = message.replace("{" + token + "}", value)
    character = context.get("character") or STATE.get("character", "")
    if character:
        message = message.replace("{c}", character)
        message = message.replace("{C}", character)
    for name, value in values.items():
        if value is None:
            continue
        message = message.replace("${" + name + "}", value)
        message = message.replace("{" + name + "}", value)
    return message


def log_message_text(line):
    return LOG_PREFIX_RE.sub("", line.rstrip("\n"))


def log_timestamp_from_line(line):
    match = LOG_TIMESTAMP_RE.match(line)
    if not match:
        return 0
    try:
        return datetime.strptime(match.group("stamp"), "%a %b %d %H:%M:%S %Y").timestamp()
    except ValueError:
        return 0


def everquest_clock_text(now=None):
    """Return the current P99/EverQuest time in the game's 12-hour format."""
    real_timestamp = time.time() if now is None else float(now)
    elapsed_game_minutes = math.floor(
        (real_timestamp - EQ_CLOCK_REFERENCE_REAL_TIMESTAMP)
        / EQ_REAL_SECONDS_PER_GAME_MINUTE
    )
    minutes_today = (EQ_CLOCK_REFERENCE_GAME_MINUTES + elapsed_game_minutes) % (24 * 60)
    hour_24, minute = divmod(minutes_today, 60)
    suffix = "AM" if hour_24 < 12 else "PM"
    hour_12 = hour_24 % 12 or 12
    return f"{hour_12}:{minute:02d} {suffix}"


def dancer_clock_text(now=None):
    """Return labeled in-game and local real-world times for the dancer."""
    real_timestamp = time.time() if now is None else float(now)
    local_time = datetime.fromtimestamp(real_timestamp).strftime("%-I:%M %p")
    return f"EQ  {everquest_clock_text(real_timestamp)}\nReal  {local_time}"


def parse_roll_line(line, now=None):
    """Pair EverQuest's two-line /random output and return one completed roll."""
    message = log_message_text(line)
    observed_at = time.time() if now is None else float(now)
    name_match = ROLL_NAME_RE.match(message)
    if name_match:
        ROLL_PENDING.update({
            "name": name_match.group("name").strip(),
            "seen_at": time.monotonic(),
        })
        return None

    value_match = ROLL_VALUE_RE.match(message)
    if not value_match:
        if ROLL_PENDING.get("name"):
            ROLL_PENDING.update({"name": "", "seen_at": 0.0})
        return None
    name = str(ROLL_PENDING.get("name") or "").strip()
    recently_seen = time.monotonic() - float(ROLL_PENDING.get("seen_at") or 0) <= 5
    ROLL_PENDING.update({"name": "", "seen_at": 0.0})
    if not name or not recently_seen:
        return None

    minimum = int(value_match.group("minimum"))
    maximum = int(value_match.group("maximum"))
    value = int(value_match.group("value"))
    if minimum > maximum or value < minimum or value > maximum:
        return None
    return {
        "name": name,
        "minimum": minimum,
        "maximum": maximum,
        "value": value,
        "created_at": observed_at,
        "expires_at": observed_at + ROLL_OVERLAY_SECONDS,
    }


def update_roll_contests(contests, roll):
    """Update one range's expiry and replace its leader only for a higher roll."""
    try:
        minimum = int(roll["minimum"])
        maximum = int(roll["maximum"])
        value = int(roll["value"])
        created_at = float(roll.get("created_at") or time.time())
        expires_at = float(roll.get("expires_at") or created_at + ROLL_OVERLAY_SECONDS)
    except (KeyError, TypeError, ValueError):
        return False
    key = (minimum, maximum)
    current = contests.get(key)
    if current is None or float(current["expires_at"]) <= created_at:
        contests[key] = dict(roll, expires_at=expires_at)
    else:
        current["expires_at"] = expires_at
        if value > int(current["value"]):
            contests[key] = dict(roll, expires_at=expires_at)
    return True


def character_from_log_path(path):
    match = re.search(r"eqlog_([^_]+)_", Path(path).name)
    return match.group(1) if match else ""


def normalize_combat_name(value):
    return re.sub(r"\s+", " ", str(value or "").strip())


def reset_dps_state(target="", start_ts=0):
    DPS_STATE.update({
        "target": normalize_combat_name(target),
        "start_ts": start_ts or 0,
        "last_ts": start_ts or 0,
        "ended_ts": 0,
        "active": bool(target),
        "total_damage": 0,
        "combatants": {},
        "hits": {},
        "proc_counts": {},
        "last_killer": "",
        "encounter_id": uuid.uuid4().hex if target else "",
    })


def is_self_dps_attacker(attacker):
    attacker = normalize_combat_name(attacker)
    if attacker.lower() == "you":
        return True
    character = normalize_combat_name(STATE.get("character"))
    return bool(character and attacker.lower() == character.lower())


def should_start_dps_encounter(attacker, target):
    return bool(normalize_combat_name(target) and is_self_dps_attacker(attacker))


def dps_payload_from_state_unlocked(state, limit=20):
    start_ts = state.get("start_ts", 0) or 0
    last_ts = state.get("ended_ts", 0) or state.get("last_ts", 0) or start_ts
    duration = max(1, int(last_ts - start_ts + 1)) if start_ts and last_ts else 0
    rows = []
    for name, damage in state.get("combatants", {}).items():
        damage = int(damage)
        rows.append({
            "name": name,
            "damage": damage,
            "dps": round(damage / duration, 2) if duration else 0,
            "hits": int(state.get("hits", {}).get(name, 0)),
        })
    rows.sort(key=lambda row: row["damage"], reverse=True)
    total_damage = int(state.get("total_damage", 0))
    proc_counts = {}
    for weapon in ("willsapper", "blade of strategy"):
        counts = state.get("proc_counts", {}).get(weapon, {})
        proc_counts[weapon] = {
            "landed": int(counts.get("landed", 0)),
            "resisted": int(counts.get("resisted", 0)),
        }
    return {
        "target": state.get("target", ""),
        "active": bool(state.get("active", False)),
        "start_ts": start_ts,
        "last_ts": last_ts,
        "duration": duration,
        "total_damage": total_damage,
        "total_dps": round(total_damage / duration, 2) if duration else 0,
        "last_killer": state.get("last_killer", ""),
        "encounter_id": state.get("encounter_id", ""),
        "rows": rows[:limit],
        "participant_count": len(rows),
        "proc_counts": proc_counts,
    }


def dps_payload_unlocked(limit=20):
    return dps_payload_from_state_unlocked(DPS_STATE, limit=limit)


def dps_history_summary(payload):
    return {
        "encounter_id": payload.get("encounter_id", ""),
        "target": payload.get("target", ""),
        "active": bool(payload.get("active", False)),
        "start_ts": payload.get("start_ts", 0),
        "last_ts": payload.get("last_ts", 0),
        "duration": payload.get("duration", 0),
        "total_damage": payload.get("total_damage", 0),
        "total_dps": payload.get("total_dps", 0),
        "participant_count": payload.get("participant_count", 0),
        "last_killer": payload.get("last_killer", ""),
    }


def remember_dps_encounter_unlocked():
    payload = dps_payload_unlocked(limit=200)
    if not payload.get("encounter_id") or not payload.get("target") or not payload.get("total_damage"):
        return None
    existing_index = next(
        (index for index, item in enumerate(DPS_HISTORY) if item.get("encounter_id") == payload.get("encounter_id")),
        None,
    )
    if existing_index is None:
        DPS_HISTORY.insert(0, payload)
    else:
        DPS_HISTORY[existing_index] = payload
    del DPS_HISTORY[DPS_HISTORY_MAX:]
    return payload


def dps_filter_range(filter_preset="", custom_start_ts=0, custom_end_ts=0):
    now = time.time()
    preset = str(filter_preset or "all").strip().lower()
    if preset in ("current", "live"):
        return preset, 0, 0
    if preset in ("hour", "last_hour"):
        return preset, now - 3600, now
    if preset in ("day", "last_day"):
        return preset, now - 86400, now
    if preset in ("week", "last_week"):
        return preset, now - 604800, now
    if preset == "custom":
        start = float(custom_start_ts or 0)
        end = float(custom_end_ts or 0) or now
        return preset, start, end
    return "all", 0, 0


def dps_filtered_encounters_unlocked(filter_preset="all", custom_start_ts=0, custom_end_ts=0, include_current=True):
    preset, start_ts, end_ts = dps_filter_range(filter_preset, custom_start_ts, custom_end_ts)
    encounters = []
    seen = set()
    if include_current and DPS_STATE.get("encounter_id") and DPS_STATE.get("target"):
        current = dps_payload_unlocked(limit=200)
        if current.get("total_damage"):
            encounters.append(current)
            seen.add(current.get("encounter_id"))
    if preset not in ("current", "live"):
        for payload in DPS_HISTORY:
            encounter_id = payload.get("encounter_id", "")
            if not encounter_id or encounter_id in seen:
                continue
            last_ts = float(payload.get("last_ts") or payload.get("start_ts") or 0)
            if start_ts and last_ts < start_ts:
                continue
            if end_ts and last_ts > end_ts:
                continue
            encounters.append(payload)
            seen.add(encounter_id)
    encounters.sort(key=lambda item: float(item.get("last_ts") or item.get("start_ts") or 0), reverse=True)
    return encounters


def dps_view_config():
    with CONFIG_LOCK:
        section = dict(DEFAULT_CONFIG["nparse"]["dps"])
        section.update(CONFIG.get("nparse", {}).get("dps", {}))
    return section


def dps_payload(limit=20, encounter_id="", filter_preset=None, custom_start_ts=None, custom_end_ts=None):
    section = dps_view_config()
    selected_id = str(encounter_id if encounter_id is not None else section.get("selected_encounter_id", "")).strip()
    if encounter_id == "":
        selected_id = str(section.get("selected_encounter_id", "") or "").strip()
    preset = section.get("filter_preset", "all") if filter_preset is None else filter_preset
    start = section.get("custom_start_ts", 0) if custom_start_ts is None else custom_start_ts
    end = section.get("custom_end_ts", 0) if custom_end_ts is None else custom_end_ts
    with DPS_LOCK:
        encounters = dps_filtered_encounters_unlocked(preset, start, end)
        selected = None
        if selected_id:
            selected = next((item for item in encounters if item.get("encounter_id") == selected_id), None)
        if selected is None:
            selected = encounters[0] if encounters else dps_payload_unlocked(limit=200)
        payload = dict(selected)
        rows = list(payload.get("rows") or [])
        payload["rows"] = rows[:limit]
        payload["participant_count"] = len(rows)
        payload["selected_encounter_id"] = payload.get("encounter_id", "")
        payload["encounters"] = [dps_history_summary(item) for item in encounters]
        payload["filter_preset"] = preset
        payload["custom_start_ts"] = start
        payload["custom_end_ts"] = end
        return payload


def select_dps_encounter(direction="latest", encounter_id=""):
    direction = str(direction or "latest").strip().lower()
    with CONFIG_LOCK:
        nparse = dict(CONFIG.get("nparse", DEFAULT_CONFIG["nparse"]))
        section = dict(DEFAULT_CONFIG["nparse"]["dps"])
        section.update(nparse.get("dps", {}))
    with DPS_LOCK:
        encounters = dps_filtered_encounters_unlocked(
            section.get("filter_preset", "all"),
            section.get("custom_start_ts", 0),
            section.get("custom_end_ts", 0),
        )
        ids = [item.get("encounter_id", "") for item in encounters if item.get("encounter_id")]
    current_id = str(section.get("selected_encounter_id", "") or "").strip()
    next_id = current_id
    if direction in ("live", "current"):
        next_id = ""
    elif encounter_id:
        next_id = str(encounter_id).strip()
    elif ids:
        if direction == "prev":
            index = ids.index(current_id) if current_id in ids else 0
            next_id = ids[(index - 1) % len(ids)]
        elif direction == "next":
            index = ids.index(current_id) if current_id in ids else -1
            next_id = ids[(index + 1) % len(ids)]
        else:
            next_id = ids[0]
    with CONFIG_LOCK:
        nparse = dict(CONFIG.get("nparse", DEFAULT_CONFIG["nparse"]))
        section = dict(DEFAULT_CONFIG["nparse"]["dps"])
        section.update(nparse.get("dps", {}))
        section["selected_encounter_id"] = next_id
        nparse["dps"] = section
        CONFIG["nparse"] = nparse
        save_config(CONFIG)
    return dps_payload(encounter_id=next_id)


def add_dps_damage(attacker, target, damage, timestamp):
    attacker = normalize_combat_name(attacker)
    target = normalize_combat_name(target)
    is_self_attack = is_self_dps_attacker(attacker)
    if attacker.lower() == "you":
        attacker = STATE.get("character") or "You"
    damage = int(damage or 0)
    if not attacker or not target or damage <= 0:
        return None

    with DPS_LOCK:
        active_target = DPS_STATE.get("target", "")
        last_ts = DPS_STATE.get("last_ts", 0) or 0
        idle = bool(last_ts and timestamp and timestamp - last_ts > DPS_IDLE_SECONDS)
        self_target_change = bool(
            active_target
            and active_target.lower() != target.lower()
            and is_self_attack
        )
        if not active_target or idle or not DPS_STATE.get("active", False) or self_target_change:
            if not is_self_attack:
                return None
            if active_target:
                DPS_STATE["active"] = False
                DPS_STATE["ended_ts"] = DPS_STATE.get("ended_ts") or last_ts or timestamp or time.time()
                remember_dps_encounter_unlocked()
            reset_dps_state(target, timestamp)
            active_target = target
        if active_target.lower() != target.lower():
            return None

        DPS_STATE["active"] = True
        DPS_STATE["last_ts"] = timestamp or time.time()
        if not DPS_STATE.get("start_ts"):
            DPS_STATE["start_ts"] = DPS_STATE["last_ts"]
        DPS_STATE["total_damage"] = int(DPS_STATE.get("total_damage", 0)) + damage
        combatants = DPS_STATE.setdefault("combatants", {})
        hits = DPS_STATE.setdefault("hits", {})
        combatants[attacker] = int(combatants.get(attacker, 0)) + damage
        hits[attacker] = int(hits.get(attacker, 0)) + 1
        return dps_payload_unlocked()


def add_dps_proc(message, timestamp):
    """Count the two requested weapon proc outcomes on the active self encounter."""
    message_lower = normalize_combat_name(message).lower()
    with DPS_LOCK:
        target = normalize_combat_name(DPS_STATE.get("target"))
        last_ts = float(DPS_STATE.get("last_ts") or 0)
        if (
            not target
            or not DPS_STATE.get("active", False)
            or (last_ts and timestamp and timestamp - last_ts > DPS_IDLE_SECONDS)
        ):
            return None
        matched = None
        for weapon in ("willsapper", "blade of strategy"):
            profile = AGGRO_WEAPON_PROFILES[weapon]
            if message_lower == profile.get("proc_resist", ""):
                matched = (weapon, "resisted")
                break
            if message_lower == f"{target.lower()} {profile.get('proc_land', '')}":
                matched = (weapon, "landed")
                break
        if not matched:
            return None
        weapon, outcome = matched
        counts = DPS_STATE.setdefault("proc_counts", {}).setdefault(
            weapon, {"landed": 0, "resisted": 0}
        )
        counts[outcome] = int(counts.get(outcome, 0)) + 1
        DPS_STATE["last_ts"] = timestamp or DPS_STATE.get("last_ts") or time.time()
        return dps_payload_unlocked()


def finish_dps_encounter(target, killer, timestamp):
    target = normalize_combat_name(target)
    killer = normalize_combat_name(killer)
    with DPS_LOCK:
        if not DPS_STATE.get("target") or DPS_STATE.get("target", "").lower() != target.lower():
            return None
        DPS_STATE["active"] = False
        DPS_STATE["ended_ts"] = timestamp or DPS_STATE.get("last_ts") or time.time()
        DPS_STATE["last_killer"] = killer
        remember_dps_encounter_unlocked()
        return dps_payload_unlocked()


def parse_dps_line(line):
    timestamp = log_timestamp_from_line(line) or time.time()
    message = log_message_text(line)
    proc_payload = add_dps_proc(message, timestamp)
    if proc_payload:
        broadcast("dps", proc_payload)
        return proc_payload
    if DPS_NON_MELEE_RE.match(message):
        return
    damage_match = DPS_DAMAGE_RE.match(message)
    if damage_match:
        payload = add_dps_damage(
            damage_match.group("attacker"),
            damage_match.group("target"),
            damage_match.group("damage"),
            timestamp,
        )
        if payload:
            broadcast("dps", payload)
        return payload
    slain_match = DPS_SLAIN_RE.match(message)
    if slain_match:
        payload = finish_dps_encounter(slain_match.group("target"), slain_match.group("killer"), timestamp)
        if payload:
            broadcast("dps", payload)
        return payload
    return None


def reset_aggro_state(target="", timestamp=0):
    AGGRO_STATE.update({
        "target": normalize_combat_name(target),
        "start_ts": timestamp or 0,
        "last_ts": timestamp or 0,
        "active": bool(target),
        "threat": {},
        "actions": {},
        "procs": {},
        "pending_spell": "",
        "pending_spell_ts": 0,
    })


def load_aggro_inventory(force=False):
    character = normalize_combat_name(STATE.get("character"))
    active_log = Path(STATE.get("active_log") or "")
    candidates = []
    if character and active_log:
        candidates.append(active_log.parent.parent / f"{character}-Inventory.txt")
    if character:
        candidates.extend([
            Path.home() / "Games" / "EverQuest" / f"{character}-Inventory.txt",
            Path.home() / "Games" / "EverQuest-Basic" / f"{character}-Inventory.txt",
        ])
    inventory_path = next((path for path in candidates if path.is_file()), None)
    mtime = inventory_path.stat().st_mtime if inventory_path else 0
    if (
        not force
        and AGGRO_INVENTORY_CACHE.get("character") == character
        and AGGRO_INVENTORY_CACHE.get("path") == str(inventory_path or "")
        and AGGRO_INVENTORY_CACHE.get("mtime") == mtime
    ):
        return AGGRO_INVENTORY_CACHE
    primary_name = ""
    secondary_name = ""
    if inventory_path:
        try:
            for raw_line in inventory_path.read_text(encoding="utf-8", errors="replace").splitlines()[1:]:
                fields = raw_line.split("\t")
                if len(fields) < 2:
                    continue
                if fields[0].strip().lower() == "primary":
                    primary_name = fields[1].strip()
                elif fields[0].strip().lower() == "secondary":
                    secondary_name = fields[1].strip()
        except OSError:
            pass
    AGGRO_INVENTORY_CACHE.update({
        "character": character,
        "path": str(inventory_path or ""),
        "mtime": mtime,
        "primary_name": primary_name,
        "secondary_name": secondary_name,
        "primary": AGGRO_WEAPON_PROFILES.get(primary_name.lower()),
        "secondary": AGGRO_WEAPON_PROFILES.get(secondary_name.lower()),
    })
    return AGGRO_INVENTORY_CACHE


def aggro_class_for(name):
    return AGGRO_CLASS_CACHE.get(normalize_combat_name(name).lower(), {}).get("class", "")


def load_recent_aggro_who_cache(path, max_bytes=8 * 1024 * 1024):
    log_path = Path(path or "")
    if not log_path.is_file():
        return
    try:
        with log_path.open("rb") as handle:
            size = handle.seek(0, os.SEEK_END)
            handle.seek(max(0, size - max_bytes), os.SEEK_SET)
            data = handle.read().decode("utf-8", errors="replace")
    except OSError:
        return
    for raw_line in data.splitlines():
        message = log_message_text(raw_line)
        match = AGGRO_WHO_RE.match(message)
        if not match:
            continue
        title = normalize_combat_name(match.group("title")).lower()
        player_class = AGGRO_TITLE_CLASSES.get(title, "")
        if player_class:
            AGGRO_CLASS_CACHE[match.group("name").lower()] = {
                "name": match.group("name"),
                "class": player_class,
                "level": int(match.group("level")),
                "title": match.group("title"),
                "seen_ts": log_timestamp_from_line(raw_line) or 0,
            }


def estimated_aggro_swing_threat(attacker, verb, damage=0):
    attacker = normalize_combat_name(attacker)
    verb = {
        "hits": "hit", "slashes": "slash", "crushes": "crush",
        "pierces": "pierce", "punches": "punch", "kicks": "kick",
        "bashes": "bash",
    }.get(str(verb or "").lower(), str(verb or "").lower())
    if verb == "kick":
        return 5
    if verb == "bash":
        return 7
    if is_self_dps_attacker(attacker):
        inventory = load_aggro_inventory()
        primary = inventory.get("primary")
        secondary = inventory.get("secondary")
        if primary and primary.get("two_handed") and primary.get("type") == verb:
            return float(primary.get("damage", 0) + primary.get("damage_bonus", 0))
        if primary and secondary and primary.get("type") == secondary.get("type") == verb:
            return round(
                (primary.get("damage", 0) + 11) * 0.55
                + (secondary.get("damage", 0) + 12) * 0.45,
                2,
            )
        if primary and primary.get("type") == verb:
            return float(primary.get("damage", 0) + 11)
        if secondary and secondary.get("type") == verb:
            return float(secondary.get("damage", 0) + 12)
    player_class = aggro_class_for(STATE.get("character") if is_self_dps_attacker(attacker) else attacker)
    if player_class:
        return float(AGGRO_CLASS_SWING_THREAT.get(player_class, 20))
    if damage:
        return float(max(12, min(35, int(damage) // 2 + 11)))
    return 20.0


def aggro_payload_unlocked():
    start_ts = float(AGGRO_STATE.get("start_ts") or 0)
    last_ts = float(AGGRO_STATE.get("last_ts") or start_ts)
    duration = max(1, int(last_ts - start_ts + 1)) if start_ts else 0
    threat_map = AGGRO_STATE.get("threat", {})
    leader_threat = max([float(value) for value in threat_map.values()] or [0])
    character = normalize_combat_name(STATE.get("character"))
    inventory = load_aggro_inventory()
    rows = []
    for name, value in threat_map.items():
        threat = max(0.0, float(value))
        is_self = bool(character and name.lower() == character.lower())
        player_class = aggro_class_for(name)
        if is_self and inventory.get("primary") and (
            inventory.get("secondary") or inventory.get("secondary_name", "").lower() in ("", "empty")
        ):
            confidence = "weapon"
        elif player_class:
            confidence = "class"
        else:
            confidence = "generic"
        rows.append({
            "name": name,
            "threat": round(threat, 1),
            "threat_per_minute": round(threat / duration * 60, 1) if duration else 0,
            "flux": int(threat / 50),
            "percent": round(threat / leader_threat * 100, 1) if leader_threat else 0,
            "actions": int(AGGRO_STATE.get("actions", {}).get(name, 0)),
            "procs": int(AGGRO_STATE.get("procs", {}).get(name, 0)),
            "class": player_class,
            "confidence": confidence,
            "is_self": is_self,
        })
    rows.sort(key=lambda row: row["threat"], reverse=True)
    return {
        "target": AGGRO_STATE.get("target", ""),
        "active": bool(AGGRO_STATE.get("active", False)),
        "start_ts": start_ts,
        "last_ts": last_ts,
        "duration": duration,
        "rows": rows,
        "estimated": True,
        "source": "local combat log",
        "known_classes": len(AGGRO_CLASS_CACHE),
        "inventory": {
            "path": inventory.get("path", ""),
            "primary": inventory.get("primary_name", ""),
            "secondary": inventory.get("secondary_name", ""),
            "primary_known": bool(inventory.get("primary")),
            "secondary_known": bool(inventory.get("secondary")),
        },
    }


def aggro_payload():
    with AGGRO_LOCK:
        return aggro_payload_unlocked()


def add_aggro_threat(attacker, target, amount, timestamp, is_self_action=False, is_proc=False):
    attacker = normalize_combat_name(attacker)
    target = normalize_combat_name(target)
    if attacker.lower() == "you":
        attacker = STATE.get("character") or "You"
    if not attacker or not target:
        return None
    timestamp = timestamp or time.time()
    with AGGRO_LOCK:
        active_target = normalize_combat_name(AGGRO_STATE.get("target"))
        last_ts = float(AGGRO_STATE.get("last_ts") or 0)
        idle = bool(last_ts and timestamp - last_ts > AGGRO_IDLE_SECONDS)
        target_change = bool(active_target and active_target.lower() != target.lower() and is_self_action)
        if not active_target or idle or not AGGRO_STATE.get("active", False) or target_change:
            if not is_self_action:
                return None
            reset_aggro_state(target, timestamp)
            active_target = target
        if active_target.lower() != target.lower():
            return None
        AGGRO_STATE["active"] = True
        AGGRO_STATE["last_ts"] = timestamp
        threat = AGGRO_STATE.setdefault("threat", {})
        actions = AGGRO_STATE.setdefault("actions", {})
        procs = AGGRO_STATE.setdefault("procs", {})
        threat[attacker] = max(0.0, float(threat.get(attacker, 0)) + float(amount))
        actions[attacker] = int(actions.get(attacker, 0)) + 1
        if is_proc:
            procs[attacker] = int(procs.get(attacker, 0)) + 1
        return aggro_payload_unlocked()


def finish_aggro_encounter(target):
    target = normalize_combat_name(target)
    with AGGRO_LOCK:
        if target and AGGRO_STATE.get("target", "").lower() != target.lower():
            return None
        AGGRO_STATE["active"] = False
        return aggro_payload_unlocked()


def parse_aggro_line(line):
    timestamp = log_timestamp_from_line(line) or time.time()
    message = log_message_text(line)
    payload = None

    who_match = AGGRO_WHO_RE.match(message)
    if who_match:
        title = normalize_combat_name(who_match.group("title")).lower()
        player_class = AGGRO_TITLE_CLASSES.get(title, "")
        if player_class:
            AGGRO_CLASS_CACHE[who_match.group("name").lower()] = {
                "name": who_match.group("name"),
                "class": player_class,
                "level": int(who_match.group("level")),
                "title": who_match.group("title"),
                "seen_ts": timestamp,
            }
        return None

    cast_match = AGGRO_CAST_RE.match(message)
    if cast_match:
        with AGGRO_LOCK:
            AGGRO_STATE["pending_spell"] = cast_match.group("spell").lower()
            AGGRO_STATE["pending_spell_ts"] = timestamp
        return None
    if message == "Your spell is interrupted.":
        with AGGRO_LOCK:
            AGGRO_STATE["pending_spell"] = ""
            AGGRO_STATE["pending_spell_ts"] = 0
        return None

    inventory = load_aggro_inventory()
    equipped_profiles = {}
    for slot in ("primary", "secondary"):
        profile = inventory.get(slot)
        name = inventory.get(f"{slot}_name", "")
        if profile and profile.get("proc_threat"):
            equipped_profiles[name.lower()] = profile
    message_lower = message.lower()
    with AGGRO_LOCK:
        proc_target = normalize_combat_name(AGGRO_STATE.get("target"))
    for profile in equipped_profiles.values():
        proc_resist = profile.get("proc_resist", "")
        proc_land = profile.get("proc_land", "")
        proc_landed = bool(proc_land and proc_target and message_lower == f"{proc_target.lower()} {proc_land}")
        if (proc_resist and message_lower == proc_resist) or proc_landed:
            if proc_target:
                payload = add_aggro_threat(
                    "You",
                    proc_target,
                    profile.get("proc_threat", 0),
                    timestamp,
                    True,
                    is_proc=True,
                )
                if payload:
                    broadcast("aggro", payload)
                return payload

    damage_match = DPS_DAMAGE_RE.match(message)
    if damage_match:
        attacker = damage_match.group("attacker")
        target = damage_match.group("target")
        damage = int(damage_match.group("damage"))
        is_self = is_self_dps_attacker(attacker)
        verb = damage_match.group("verb").lower()
        amount = estimated_aggro_swing_threat(attacker, verb, damage)
        payload = add_aggro_threat(attacker, target, amount, timestamp, is_self)
    else:
        miss_match = AGGRO_ANY_MISS_RE.match(message)
        if miss_match:
            attacker = miss_match.group("attacker")
            is_self = is_self_dps_attacker(attacker)
            amount = estimated_aggro_swing_threat(attacker, miss_match.group("verb"))
            payload = add_aggro_threat(attacker, miss_match.group("target"), amount, timestamp, is_self)

    with AGGRO_LOCK:
        pending_spell = AGGRO_STATE.get("pending_spell", "")
        pending_ts = float(AGGRO_STATE.get("pending_spell_ts") or 0)
        current_target = AGGRO_STATE.get("target", "")
    if pending_spell and timestamp - pending_ts <= 6:
        spell_target = ""
        spell_threat = 0
        if pending_spell == "flame lick":
            match = re.match(r"^(?P<target>.+?) is surrounded by flickering flames\.$", message, re.IGNORECASE)
            if match:
                spell_target, spell_threat = match.group("target"), 1206
        elif pending_spell == "enveloping roots":
            match = re.match(r"^(?P<target>.+?)'s feet become entwined\.$", message, re.IGNORECASE)
            if match:
                spell_target, spell_threat = match.group("target"), 1310
        elif pending_spell in ("jolt", "cinder jolt"):
            match = re.match(r"^(?P<target>.+?)'s head snaps back\.$", message, re.IGNORECASE)
            if match:
                spell_target, spell_threat = match.group("target"), -500
        if message.lower() == f"your target resisted the {pending_spell} spell.":
            spell_target = current_target
            spell_threat = -500 if "jolt" in pending_spell else 1200 if pending_spell == "flame lick" else 1310
        if spell_target and spell_threat:
            payload = add_aggro_threat("You", spell_target, spell_threat, timestamp, True)
            with AGGRO_LOCK:
                AGGRO_STATE["pending_spell"] = ""
                AGGRO_STATE["pending_spell_ts"] = 0

    slain_target = ""
    if message.startswith("You have slain ") and message.endswith("!"):
        slain_target = message[len("You have slain "):-1]
    else:
        slain_match = DPS_SLAIN_RE.match(message)
        if slain_match:
            slain_target = slain_match.group("target")
    if slain_target:
        payload = finish_aggro_encounter(slain_target) or payload
    if message in ("LOADING, PLEASE WAIT...", "Welcome to EverQuest!") or ZONE_ENTER_RE.match(message):
        with AGGRO_LOCK:
            reset_aggro_state()
            payload = aggro_payload_unlocked()
    if payload:
        broadcast("aggro", payload)
    return payload


def child_text(element, name, default=""):
    child = element.find(name)
    return child.text if child is not None and child.text is not None else default


def child_bool(element, name, default=False):
    value = child_text(element, name, str(default))
    return value.strip().lower() == "true"


def import_gina_package(path):
    import xml.etree.ElementTree as ET

    package_path = Path(path).expanduser()
    if not package_path.exists() or package_path.suffix.lower() != ".gtp":
        raise ValueError(f"Not a GINA package: {package_path}")

    with zipfile.ZipFile(package_path) as archive:
        data = archive.read("ShareData.xml")
    root = ET.fromstring(data)

    imported = []
    skipped = []

    def walk_group(group, group_path):
        name = child_text(group, "Name", "").strip()
        next_path = group_path + ([name] if name else [])
        triggers = group.find("Triggers")
        if triggers is not None:
            for trigger in triggers.findall("Trigger"):
                trigger_name = child_text(trigger, "Name", "Imported Trigger").strip() or "Imported Trigger"
                trigger_text = child_text(trigger, "TriggerText", "")
                enable_regex = child_bool(trigger, "EnableRegex", True)
                pattern = gina_pattern_to_python(trigger_text, enable_regex)
                try:
                    re.compile(pattern, re.IGNORECASE)
                except re.error as exc:
                    skipped.append({"name": trigger_name, "pattern": trigger_text, "error": str(exc)})
                    continue

                display_text = child_text(trigger, "DisplayText", "").strip()
                voice_text = child_text(trigger, "TextToVoiceText", "").strip()
                timer_name = child_text(trigger, "TimerName", "").strip()
                category = child_text(trigger, "Category", "").strip()
                timer_type = child_text(trigger, "TimerType", "").strip().lower()
                timer_seconds = 0
                if timer_type == "timer":
                    timer_seconds = int(float(child_text(trigger, "TimerDuration", "0") or 0))
                    if timer_seconds <= 0:
                        timer_seconds = int(float(child_text(trigger, "TimerMillisecondDuration", "0") or 0) / 1000)

                message = display_text or voice_text or timer_name or trigger_name
                imported_trigger = {
                    "id": "gina-" + str(uuid.uuid4()),
                    "name": trigger_name,
                    "pattern": pattern,
                    "message": message,
                    "display_text": display_text,
                    "voice_text": voice_text,
                    "timer_name": timer_name,
                    "timer_seconds": timer_seconds,
                    "dynamic_timer": "{TS}" in trigger_text or "{ts}" in trigger_text or child_bool(trigger, "TimerHasDynamicDuration", False),
                    "enabled": True,
                    "source": package_path.name,
                    "category": category,
                    "group": " / ".join(next_path),
                    "use_text": child_bool(trigger, "UseText", False),
                    "use_voice": child_bool(trigger, "UseTextToVoice", False),
                }
                imported_trigger = normalize_imported_trigger(imported_trigger)
                imported_trigger["color"] = trigger_palette_color(imported_trigger)
                imported.append(imported_trigger)
        groups = group.find("TriggerGroups")
        if groups is not None:
            for child in groups.findall("TriggerGroup"):
                walk_group(child, next_path)

    groups = root.find("TriggerGroups")
    if groups is not None:
        for group in groups.findall("TriggerGroup"):
            walk_group(group, [])

    with CONFIG_LOCK:
        existing_keys = {
            (trigger.get("source"), trigger.get("name"), trigger.get("pattern"))
            for trigger in CONFIG.get("triggers", [])
        }
        added = []
        for trigger in imported:
            key = (trigger.get("source"), trigger.get("name"), trigger.get("pattern"))
            if key in existing_keys:
                continue
            CONFIG.setdefault("triggers", []).append(trigger)
            existing_keys.add(key)
            added.append(trigger)
        save_config(CONFIG)

    return {"package": str(package_path), "imported": len(added), "skipped": skipped}


def compile_triggers(config):
    compiled = []
    for trigger in config.get("triggers", []):
        if not trigger.get("enabled", True):
            continue
        try:
            compiled.append((trigger, re.compile(trigger.get("pattern", ""), re.IGNORECASE)))
        except re.error as exc:
            broadcast("error", {"message": f"Bad regex in {trigger.get('name', 'trigger')}: {exc}"})
    for trigger in build_nparse_custom_triggers():
        try:
            compiled.append((trigger, re.compile(trigger.get("pattern", ""), re.IGNORECASE)))
        except re.error:
            continue
    return compiled


def resolve_nparse_zone_key(zone_name):
    norm = normalize_nparse_key(zone_name)
    if not norm:
        return ""
    if norm in NPARSE_LIBRARY["zones"]:
        return norm
    alias = NPARSE_LIBRARY["alias_to_key"].get(norm, "")
    if alias:
        alias_norm = normalize_nparse_key(alias)
        if alias_norm in NPARSE_LIBRARY["zones"]:
            return alias_norm
        if alias in NPARSE_LIBRARY["zones"]:
            return alias
        for key, zone in NPARSE_LIBRARY["zones"].items():
            if normalize_nparse_key(zone.get("label", "")) == alias_norm or normalize_nparse_key(key) == alias_norm:
                return key
    return ""


def resolve_nparse_zone(zone_name):
    zone_key = resolve_nparse_zone_key(zone_name)
    zone = NPARSE_LIBRARY["zones"].get(zone_key, {})
    if zone_key:
        return zone.get("label", zone_name), zone_key
    return zone_name, ""


def current_nparse_zone_name():
    with CONFIG_LOCK:
        selected = CONFIG.get("nparse", {}).get("maps", {}).get("selected_zone", "")
    return STATE.get("zone") or selected or NPARSE_LIBRARY.get("last_zone", "")


def current_nparse_zone_key():
    return resolve_nparse_zone_key(current_nparse_zone_name())


def current_nparse_zone_record():
    zone_key = current_nparse_zone_key()
    if not zone_key:
        return {}
    return NPARSE_LIBRARY["zones"].get(zone_key, {})


def current_nparse_zone_timer():
    zone_key = current_nparse_zone_key()
    if not zone_key:
        return {}
    return NPARSE_LIBRARY["zone_timers"].get(normalize_nparse_key(zone_key), {})


def zone_from_line(line):
    message = log_message_text(line)
    match = ZONE_ENTER_RE.search(message)
    if match:
        zone = match.group("zone").strip()
        return "" if normalize_nparse_key(zone) == "everquest" else zone
    match = WHO_COUNT_RE.search(message)
    if match:
        zone = match.group("zone").strip()
        return "" if normalize_nparse_key(zone) == "everquest" else zone
    match = WHO_ZONE_RE.search(message)
    if match:
        zone = match.group("zone").strip()
        return "" if normalize_nparse_key(zone) == "everquest" else zone
    return ""


def location_from_line(line):
    message = log_message_text(line)
    match = LOCATION_RE.search(message)
    if not match:
        return None
    try:
        return (
            float(match.group("x")),
            float(match.group("y")),
            float(match.group("z")),
        )
    except ValueError:
        return None


def heading_from_line(line):
    message = log_message_text(line)
    match = HEADING_RE.search(message)
    if not match:
        return ""
    return match.group("heading").strip()


def chat_payload_from_line(line):
    message = log_message_text(line)
    first_quote = message.find("'")
    last_quote = message.rfind("'")
    if first_quote >= 0 and last_quote > first_quote:
        return message[first_quote + 1:last_quote].strip()
    return message.strip()


def is_guild_chat_line(line):
    return bool(GUILD_CHAT_RE.search(log_message_text(line)))


def ch_chain_filter_mode(section):
    mode = str(section.get("filter_mode") or "").strip()
    if mode:
        return mode
    return "guild_only" if bool(section.get("guild_only", False)) else "recent_current_or_guild"


def is_recent_log_line(line, recent_seconds, now=None):
    stamp = log_timestamp_from_line(line)
    if not stamp:
        return True
    now = time.time() if now is None else now
    return stamp <= now + 60 and now - stamp <= max(1, int(recent_seconds or 300))


def should_parse_ch_chain_line(line, section, require_recent=False):
    mode = ch_chain_filter_mode(section)
    recent_seconds = int(section.get("recent_seconds") or 300)
    guild_line = is_guild_chat_line(line)
    recent_line = is_recent_log_line(line, recent_seconds)

    if require_recent and not recent_line:
        return False
    if mode == "all_current_log":
        return True
    if mode == "guild_only":
        return guild_line
    if mode == "recent_current_only":
        return recent_line
    if mode in {"guild_style", "gg_style", "ca_style", "la_style", "tagged_styles"}:
        hit = parse_ch_chain_line(line)
        if not hit:
            return False
        tag = str(hit.get("tag") or "").upper()
        if mode == "guild_style":
            return guild_line and not tag
        if mode == "tagged_styles":
            return tag in {"GG", "CA", "LA"}
        return tag == mode.split("_", 1)[0].upper()
    return guild_line or recent_line


def ch_position_candidates(text):
    candidates = []
    for match in CH_RAMP_RE.finditer(text):
        number = int(match.group("number"))
        if 1 <= number <= 999:
            candidates.append({
                "token": match.group(0),
                "display": f"R{number}",
                "sort": 10000 + number,
                "start": match.start(),
                "end": match.end(),
                "ramp": True,
            })
    for match in CH_NUMERIC_POSITION_RE.finditer(text):
        token = match.group("position")
        number = int(token)
        if 1 <= number <= 999:
            candidates.append({
                "token": token,
                "display": str(number),
                "sort": number,
                "start": match.start(),
                "end": match.end(),
                "ramp": False,
            })
    for match in CH_LETTER_POSITION_RE.finditer(text):
        token = match.group("position")
        if token.lower() == "ch":
            continue
        if len(set(token.upper())) == 1:
            letter_value = ord(token.upper()[0]) - ord("A") + 1
            candidates.append({
                "token": token,
                "display": token.upper(),
                "sort": 20000 + letter_value,
                "start": match.start(),
                "end": match.end(),
                "ramp": False,
            })
    return sorted(candidates, key=lambda item: item["start"])


def parse_ch_chain_line(line):
    payload = chat_payload_from_line(line)
    ch_match = CH_WORD_RE.search(payload)
    rch_match = CH_RCH_RE.search(payload)
    candidates = ch_position_candidates(payload)
    if not candidates:
        return None

    chain_word_match = ch_match or rch_match
    if chain_word_match:
        before_candidates = [item for item in candidates if item["end"] <= chain_word_match.start()]
        after_candidates = [item for item in candidates if item["start"] >= chain_word_match.end()]
        position = before_candidates[-1] if before_candidates else after_candidates[0]
        if not before_candidates:
            before_text = payload[:position["start"]]
            after_text = payload[position["end"]:]
            if not CH_CHAIN_TAG_RE.search(before_text) and not re.search(r"(?:--|-\s*)\S+", after_text):
                return None
    else:
        tagged_candidates = [
            item for item in candidates
            if CH_CHAIN_TAG_RE.search(payload[:item["start"]])
            and re.search(r"(?:--|-\s*)\S+", payload[item["end"]:])
        ]
        if not tagged_candidates:
            return None
        position = tagged_candidates[0]

    tag = ""
    before_text = payload[:position["start"]]
    tag_matches = list(CH_CHAIN_TAG_RE.finditer(before_text))
    if tag_matches:
        tag = tag_matches[-1].group(0).upper()
    elif chain_word_match:
        tag_tokens = [
            token for token in re.findall(r"\b[A-Za-z0-9]{1,8}\b", before_text)
            if token.lower() not in {"ch", "rch"}
        ]
        if tag_tokens:
            tag = tag_tokens[-1].upper()

    target_text = payload
    for token in {position["token"], position["display"], f"RAMP{position['display'][1:]}" if position["display"].startswith("R") else ""}:
        if token:
            target_text = re.sub(rf"\b{re.escape(token)}\b", " ", target_text, flags=re.IGNORECASE)
    if tag:
        target_text = re.sub(rf"\b{re.escape(tag)}\b", " ", target_text, flags=re.IGNORECASE)
    target_text = CH_WORD_RE.sub(" ", target_text)
    target_text = CH_RCH_RE.sub(" ", target_text)
    words = re.findall(r"[A-Za-z0-9`]+", target_text)
    target = " ".join(words).strip()
    if not target:
        target = "Unknown"

    return {
        "id": str(uuid.uuid4()),
        "tag": tag,
        "position": position["token"].upper(),
        "display": position["display"],
        "sort": position["sort"],
        "ramp": bool(position.get("ramp")) or bool(rch_match) or bool(re.fullmatch(r"[A-Z]{3}", position["display"] or "")),
        "ramp_display": "RCH" if rch_match else position["display"],
        "target": target,
        "line": payload,
        "raw_line": line.rstrip("\n"),
        "time": time.time(),
    }


def to_real_xy(x, y):
    return -float(y), -float(x)


def heading_to_bearing(heading):
    text = re.sub(r"\s+", " ", str(heading or "").strip().lower())
    headings = {
        "north": 0.0,
        "north by northeast": 22.5,
        "northeast": 45.0,
        "east by northeast": 67.5,
        "east": 90.0,
        "east by southeast": 112.5,
        "southeast": 135.0,
        "south by southeast": 157.5,
        "south": 180.0,
        "south by southwest": 202.5,
        "southwest": 225.0,
        "west by southwest": 247.5,
        "west": 270.0,
        "west by northwest": 292.5,
        "northwest": 315.0,
        "north by northwest": 337.5,
    }
    return headings.get(text)


def seed_state_from_log(path, max_lines=300):
    log_path = Path(path)
    if not log_path.exists():
        return
    zone_name, _zone_seen = last_zone_event_from_log(log_path)
    if zone_name:
        update_zone_state(zone_name, persist=False)
    lines = read_log_tail(log_path, max_bytes=262144).splitlines()[-max_lines:]
    for line in lines:
        zone_name = zone_from_line(line)
        if zone_name:
            update_zone_state(zone_name, persist=False)
        location = location_from_line(line)
        if location is not None:
            update_location_state(location=location, observed_at=log_timestamp_from_line(line))
        heading = heading_from_line(line)
        if heading:
            update_location_state(heading=heading)


def seed_ch_chain_from_log(path, max_lines=800):
    log_path = Path(path)
    if not log_path.exists():
        return
    with CONFIG_LOCK:
        section = dict(CONFIG.get("nparse", {}).get("ch_chain", {}))
    try:
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-max_lines:]
    except OSError:
        return
    for line in lines:
        if not should_parse_ch_chain_line(line, section, require_recent=True):
            continue
        hit = parse_ch_chain_line(line)
        if not hit:
            continue
        stamp = log_timestamp_from_line(line)
        if stamp:
            hit["time"] = stamp
        broadcast("ch_chain", hit)


def update_zone_state(zone_name, persist=False):
    zone_name = str(zone_name or "").strip()
    if not zone_name:
        return
    zone_label, zone_key = resolve_nparse_zone(zone_name)
    previous_zone = STATE.get("zone", "")
    STATE["zone"] = zone_name
    STATE["zone_key"] = zone_key
    if zone_name != previous_zone:
        STATE["zone_entered_at"] = time.time()
    if persist:
        with CONFIG_LOCK:
            nparse = dict(CONFIG.get("nparse", DEFAULT_CONFIG["nparse"]))
            maps = dict(DEFAULT_CONFIG["nparse"]["maps"])
            maps.update(nparse.get("maps", {}))
            maps["selected_zone"] = zone_name
            nparse["maps"] = maps
            CONFIG["nparse"] = nparse
            save_config(CONFIG)
    broadcast("status", {
        "message": f"Watching {Path(STATE.get('active_log', '')).name}" if STATE.get("active_log") else "No EverQuest log file found",
        "active_log": STATE.get("active_log", ""),
        "character": STATE.get("character", ""),
        "zone": zone_name,
        "zone_key": zone_key,
        "zone_label": zone_label,
    })


def update_location_state(location=None, heading=None, observed_at=None):
    if location is not None:
        try:
            x, y, z = location
            previous_x = STATE.get("location_x")
            previous_y = STATE.get("location_y")
            STATE["location_raw_x"] = float(x)
            STATE["location_raw_y"] = float(y)
            STATE["location_raw_z"] = float(z)
            real_x, real_y = to_real_xy(x, y)
            STATE["location_x"] = real_x
            STATE["location_y"] = real_y
            STATE["location_z"] = float(z)
            STATE["last_location_at"] = (
                time.time() if observed_at is None else float(observed_at or 0)
            )
            if previous_x is not None and previous_y is not None:
                dx = float(real_x) - float(previous_x)
                dy = float(real_y) - float(previous_y)
                distance = math.hypot(dx, dy)
                if distance >= 0.75:
                    STATE["movement_angle"] = math.atan2(dy, dx)
                    STATE["movement_distance"] = distance
        except (TypeError, ValueError):
            pass
    if heading is not None:
        STATE["heading"] = str(heading or "").strip()


def map_location_is_recent(now=None):
    last_location_at = float(STATE.get("last_location_at") or 0)
    if last_location_at <= 0:
        return False
    now = time.time() if now is None else float(now)
    return now - last_location_at <= MAP_LOCATION_FRESH_SECONDS


def should_show_maps_overlay(section, now=None):
    if not bool(section.get("toggled", False)):
        return False
    return (
        not bool(section.get("hide_when_location_stale", True))
        or map_location_is_recent(now)
    )


def nparse_payload(zone_name=None):
    zone_name = str(zone_name or current_nparse_zone_name() or "").strip()
    zone_label, zone_key = resolve_nparse_zone(zone_name)
    zone = NPARSE_LIBRARY["zones"].get(zone_key, {})
    timer = NPARSE_LIBRARY["zone_timers"].get(normalize_nparse_key(zone_key), {})
    with CONFIG_LOCK:
        maps = dict(CONFIG.get("nparse", {}).get("maps", {}))
        spells = list(CONFIG.get("nparse", {}).get("spells", {}).get("custom_timers", []))
    entered_at = STATE.get("zone_entered_at", 0) or time.time()
    return {
        "zone": zone_name,
        "zone_label": zone_label,
        "zone_key": zone_key,
        "entered_at": entered_at,
        "location_x": STATE.get("location_x"),
        "location_y": STATE.get("location_y"),
        "location_z": STATE.get("location_z"),
        "location_raw_x": STATE.get("location_raw_x"),
        "location_raw_y": STATE.get("location_raw_y"),
        "location_raw_z": STATE.get("location_raw_z"),
        "last_location_at": STATE.get("last_location_at", 0),
        "heading": STATE.get("heading", ""),
        "movement_angle": STATE.get("movement_angle"),
        "movement_distance": STATE.get("movement_distance", 0.0),
        "map": zone,
        "zone_timer": timer,
        "zones": NPARSE_LIBRARY["zone_choices"],
        "maps_config": maps,
        "custom_timers": spells,
    }


def match_line(line, compiled):
    message_line = log_message_text(line)
    for trigger, regex in compiled:
        match = regex.search(message_line)
        if match:
            counter_key = trigger.get("id") or trigger.get("name") or trigger.get("pattern")
            TRIGGER_COUNTERS[counter_key] = TRIGGER_COUNTERS.get(counter_key, 0) + 1
            timer_seconds = int(trigger.get("timer_seconds") or 0)
            if trigger.get("dynamic_timer"):
                timer_seconds = parse_timer_span(match.groupdict().get("GINA_TS_1"))
            context = {
                "counter": TRIGGER_COUNTERS[counter_key],
                "timer_seconds": timer_seconds,
                "character": STATE.get("character", ""),
            }
            message = expand_message(trigger.get("message") or trigger.get("name") or "Trigger matched", match, message_line, context)
            display_message = expand_message(trigger.get("display_text") or "", match, message_line, context)
            voice_message = expand_message(trigger.get("voice_text") or "", match, message_line, context)
            timer_name = expand_message(trigger.get("timer_name") or message, match, message_line, context)
            reminder_message = expand_message(trigger.get("reminder_message") or "", match, message_line, context)
            reminder_display_message = expand_message(
                trigger.get("reminder_display_text") or reminder_message,
                match,
                message_line,
                context,
            )
            action = normalize_timer_key(trigger.get("timer_action") or "start") or "start"
            target = trigger.get("timer_target")
            if not target:
                target = timer_name if action != "stop" else (trigger.get("timer_name") or trigger.get("name") or message)
            return {
                "id": str(uuid.uuid4()),
                "trigger_id": trigger.get("id"),
                "name": trigger.get("name", "Trigger"),
                "message": message,
                "display_message": display_message or (message if trigger.get("use_text") else ""),
                "voice_message": voice_message,
                "use_text": bool(trigger.get("use_text", False)),
                "use_voice": bool(trigger.get("use_voice", False)),
                "timer_name": timer_name,
                "timer_action": action,
                "timer_target": target,
                "line": message_line,
                "raw_line": line.rstrip("\n"),
                "timer_seconds": timer_seconds,
                "stack_timers": bool(trigger.get("stack_timers", False)),
                "ignore_if_running": bool(trigger.get("ignore_if_running", False)),
                "color": trigger.get("color", "#60a5fa"),
                "reminder_after_seconds": float(trigger.get("reminder_after_seconds") or 0),
                "reminder_name": trigger.get("reminder_name") or trigger.get("name") or "Timer reminder",
                "reminder_message": reminder_message,
                "reminder_display_message": reminder_display_message,
                "reminder_color": trigger.get("reminder_color") or trigger.get("color", "#60a5fa"),
            }
    return None


def monitor_logs():
    current_path = ""
    handle = None
    position = 0
    compiled = []
    compiled_at = 0

    while STATE["running"]:
        with CONFIG_LOCK:
            config = dict(CONFIG)
            config["triggers"] = list(CONFIG.get("triggers", []))

        if time.time() - compiled_at > 1:
            compiled = compile_triggers(config)
            compiled_at = time.time()

        configured_log = config.get("active_log", "")
        if config.get("follow_latest", True) or not configured_log:
            wanted_path = latest_log(config.get("log_dir", ""))
        else:
            wanted_path = configured_log

        if wanted_path != current_path:
            if handle:
                handle.close()
            current_path = wanted_path
            STATE["active_log"] = current_path
            STATE["character"] = character_from_log_path(current_path)
            if current_path and Path(current_path).exists():
                load_recent_aggro_who_cache(current_path)
                load_aggro_inventory(force=True)
                handle = open(current_path, "r", encoding="utf-8", errors="replace")
                seed_state_from_log(current_path)
                seed_ch_chain_from_log(current_path)
                handle.seek(0, os.SEEK_END)
                position = handle.tell()
                broadcast("status", {"message": f"Watching {Path(current_path).name}", "active_log": current_path, "character": STATE.get("character", "")})
            else:
                handle = None
                position = 0
                broadcast("status", {"message": "No EverQuest log file found", "active_log": "", "character": ""})

        if not handle:
            time.sleep(2)
            continue

        line = handle.readline()
        if not line:
            try:
                size = Path(current_path).stat().st_size
                if size < position:
                    handle.seek(0, os.SEEK_SET)
                    position = 0
            except OSError:
                current_path = ""
            time.sleep(0.25)
            continue

        position = handle.tell()
        STATE["last_line"] = log_message_text(line)
        roll = parse_roll_line(line)
        if roll:
            broadcast("roll", roll)
        parse_dps_line(line)
        parse_aggro_line(line)
        zone_name = zone_from_line(line)
        if zone_name:
            with CONFIG_LOCK:
                auto_follow = bool(CONFIG.get("nparse", {}).get("maps", {}).get("auto_follow", True))
            if auto_follow:
                update_zone_state(zone_name, persist=True)
        location = location_from_line(line)
        if location is not None:
            update_location_state(location=location)
        heading = heading_from_line(line)
        if heading:
            update_location_state(heading=heading)
        with CONFIG_LOCK:
            ch_section = dict(CONFIG.get("nparse", {}).get("ch_chain", {}))
        ch_hit = parse_ch_chain_line(line) if should_parse_ch_chain_line(line, ch_section) else None
        if ch_hit:
            broadcast("ch_chain", ch_hit)
        hit = match_line(line, compiled)
        if hit:
            STATE["last_match"] = hit["message"]
            play_trigger_audio(hit)
            broadcast("trigger", hit)
            schedule_trigger_reminder(hit)


def overlay_loop():
    try:
        import gi
        gi.require_foreign("cairo")
        import cairo
        gi.require_version("Gtk", "3.0")
        gi.require_version("Gdk", "3.0")
        gi.require_version("GdkPixbuf", "2.0")
        from gi.repository import Gdk, GLib, Gtk, Pango
        from gi.repository import GdkPixbuf
    except Exception as exc:
        broadcast("error", {"message": f"Overlay unavailable: {exc}"})
        return

    class BaseOverlay:
        section_name = ""
        title = "EQ Watcher"

        def __init__(self):
            self.drag = None
            self.config_version = -1
            self.applying_geometry = False
            self.initializing = True
            self.pending_geometry_save = None
            self.last_configure_size = None
            self.width_resize_height = None
            self.width_resize_height_until = 0.0
            self.window = Gtk.Window(title=self.title)
            self.window.get_style_context().add_class(f"gina-window-{self.section_name.replace('_', '-')}")
            self.window.set_name(f"gina-window-{self.section_name.replace('_', '-')}")
            self.window.set_app_paintable(True)
            screen = self.window.get_screen()
            visual = screen.get_rgba_visual() if screen else None
            if visual is not None:
                self.window.set_visual(visual)
            self.window.set_decorated(False)
            self.window.set_keep_above(True)
            self.window.set_resizable(True)
            self.window.set_skip_taskbar_hint(True)
            self.window.set_skip_pager_hint(True)
            self.window.set_accept_focus(False)
            self.window.set_type_hint(Gdk.WindowTypeHint.UTILITY)
            self.window.connect("draw", self.on_draw)
            self.window.connect("realize", self.on_realize)
            self.window.connect("map-event", self.on_map_event)
            self.window.connect("size-allocate", self.on_size_allocate)
            self.window.connect("configure-event", self.on_configure_event)
            self.window.connect("delete-event", self.on_delete_event)
            self.css = Gtk.CssProvider()
            Gtk.StyleContext.add_provider_for_screen(
                Gdk.Screen.get_default(),
                self.css,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
            )
            self.content = self.build_content()
            self.window.add(self.content)
            self.content.show_all()
            self.apply_config()
            self.initializing = False
            self.window.queue_draw()
            GLib.idle_add(self.finish_initial_show)

        def section(self):
            with CONFIG_LOCK:
                section = dict(DEFAULT_CONFIG["nparse"].get(self.section_name, {}))
                section.update(CONFIG.get("nparse", {}).get(self.section_name, {}))
            return section

        def save_section(self, **changes):
            with CONFIG_LOCK:
                nparse = dict(CONFIG.get("nparse", DEFAULT_CONFIG["nparse"]))
                section = dict(DEFAULT_CONFIG["nparse"].get(self.section_name, {}))
                section.update(nparse.get(self.section_name, {}))
                section.update(changes)
                nparse[self.section_name] = section
                CONFIG["nparse"] = nparse
                save_config(CONFIG)
                # This window already reflects the change it just saved.  If
                # its tick treats that CONFIG_VERSION bump as external, it
                # reapplies geometry during the active resize and creates a
                # move/resize feedback loop.
                self.config_version = CONFIG_VERSION

        def build_content(self):
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            box.get_style_context().add_class("gina-overlay")
            box.get_style_context().add_class(f"gina-overlay-{self.section_name.replace('_', '-')}")
            box.set_margin_top(8)
            box.set_margin_bottom(8)
            box.set_margin_start(8)
            box.set_margin_end(8)
            return box

        def on_draw(self, _window, cr):
            cr.set_operator(cairo.OPERATOR_SOURCE)
            cr.set_source_rgba(0, 0, 0, 0)
            cr.paint()
            cr.set_operator(cairo.OPERATOR_OVER)
            return False

        def apply_window_frame(self):
            section = self.section()
            geometry_locked = bool(section.get("lock_geometry", False))
            geometry = list(section.get("geometry") or [0, 0, 300, 300])
            while len(geometry) < 4:
                geometry.append(0)
            x, y, width, height = [int(v) for v in geometry[:4]]
            width = max(80, width)
            height = max(40, height)
            self.applying_geometry = True
            self.window.set_decorated(False if geometry_locked else not bool(section.get("frameless", True)))
            # GTK must be resizable while the initial saved dimensions are
            # mapped; freezing it beforehand collapses to the natural label size.
            self.window.set_resizable(True)
            if geometry_locked:
                # A fixed request gives GTK an authoritative size to retain when
                # set_resizable(False) is applied after the first map.
                self.window.set_size_request(width, height)
            else:
                self.window.set_size_request(80, 40)
            # Once a window is locked, config refreshes may still update colors,
            # rows, and visibility, but must not replay stale editor geometry.
            if geometry_locked and not getattr(self, "initializing", False):
                self.window.set_resizable(False)
                self.window.set_visible(bool(section.get("toggled", False)))
                self.set_click_through(True)
                self.applying_geometry = False
                return
            self.move_content_to(x, y)
            self.window.set_default_size(width, height)
            self.window.resize(width, height)
            if getattr(self, "initializing", False):
                self.window.set_visible(False)
            else:
                self.window.set_visible(bool(section.get("toggled", False)))
            self.set_click_through(bool(section.get("clickthrough", False)) or geometry_locked)

            def enforce_geometry():
                self.move_content_to(x, y)
                self.window.resize(width, height)
                self.window.set_resizable(not bool(self.section().get("lock_geometry", False)))
                current_section = self.section()
                self.set_click_through(
                    bool(current_section.get("clickthrough", False))
                    or bool(current_section.get("lock_geometry", False))
                )
                GLib.timeout_add(250, self.clear_applying_geometry)
                return False

            GLib.timeout_add(100, enforce_geometry)

        def clear_applying_geometry(self):
            self.applying_geometry = False
            return False

        def finish_initial_show(self):
            section = self.section()
            self.window.set_visible(bool(section.get("toggled", False)))
            self.window.queue_draw()
            self.set_click_through(
                bool(section.get("clickthrough", False)) or bool(section.get("lock_geometry", False))
            )
            return False

        def window_origin(self):
            gdk_window = self.window.get_window()
            if not gdk_window:
                return self.window.get_position()
            try:
                origin = gdk_window.get_origin()
                if isinstance(origin, tuple) and len(origin) == 3:
                    return int(origin[1]), int(origin[2])
                if isinstance(origin, tuple) and len(origin) == 2:
                    return int(origin[0]), int(origin[1])
            except Exception:
                pass
            return self.window.get_position()

        def frame_offsets(self):
            gdk_window = self.window.get_window()
            if not gdk_window:
                return 0, 0
            try:
                origin_x, origin_y = self.window_origin()
                extents = gdk_window.get_frame_extents()
                return int(origin_x - extents.x), int(origin_y - extents.y)
            except Exception:
                return 0, 0

        def move_content_to(self, x, y):
            # Frameless GDK coordinates already describe the content origin.
            # Applying decorated-window frame offsets here produces a vertical
            # jump while an edit title bar is being removed.
            if bool(self.section().get("frameless", True)):
                self.window.move(int(x), int(y))
                return
            offset_x, offset_y = self.frame_offsets()
            self.window.move(int(x) - offset_x, int(y) - offset_y)

        def current_content_geometry(self, fallback_width=None, fallback_height=None):
            content_width, content_height = self.window.get_size()
            width = int(fallback_width or content_width or self.window.get_allocated_width())
            height = int(fallback_height or content_height or self.window.get_allocated_height())
            x, y = self.window_origin()
            return [int(x), int(y), max(80, width), max(40, height)]

        def save_current_geometry(self, fallback_width=None, fallback_height=None):
            self.pending_geometry_save = None
            geometry = self.current_content_geometry(fallback_width, fallback_height)
            self.save_section(geometry=geometry[:4])
            return False

        def on_configure_event(self, _window, event):
            section = self.section()
            event_width = int(getattr(event, "width", 0) or 0)
            event_height = int(getattr(event, "height", 0) or 0)
            if (self.applying_geometry or bool(section.get("lock_geometry", False))
                    or bool(section.get("frameless", True)) or not bool(section.get("toggled", False))):
                if event_width > 0 and event_height > 0:
                    self.last_configure_size = (event_width, event_height)
                return False
            now = time.monotonic()
            last_size = self.last_configure_size
            if bool(section.get("lock_height_on_width_resize", False)) and last_size:
                last_width, last_height = last_size
                if event_width > 0 and event_width != last_width:
                    self.width_resize_height = last_height
                    self.width_resize_height_until = now + 0.75
                locked_height = self.width_resize_height
                if (locked_height and now < self.width_resize_height_until
                        and event_height > 0 and event_height != locked_height):
                    self.window.resize(max(80, event_width), max(40, int(locked_height)))
                    self.last_configure_size = (event_width, int(locked_height))
                    return False
            if event_width > 0 and event_height > 0:
                self.last_configure_size = (event_width, event_height)
            if self.pending_geometry_save is not None:
                try:
                    GLib.source_remove(self.pending_geometry_save)
                except Exception:
                    pass
            self.pending_geometry_save = GLib.timeout_add(
                250,
                self.save_current_geometry,
                event_width,
                event_height,
            )
            return False

        def on_delete_event(self, _window, _event):
            """Treat the title-bar X as 'finish editing', never as destroy."""
            section = self.section()
            geometry_locked = bool(section.get("lock_geometry", False))
            if geometry_locked:
                geometry = list(section.get("geometry") or [0, 0, 300, 300])[:4]
            else:
                geometry = self.current_content_geometry()
            if self.pending_geometry_save is not None:
                try:
                    GLib.source_remove(self.pending_geometry_save)
                except Exception:
                    pass
                self.pending_geometry_save = None
            self.drag = None
            self.applying_geometry = True
            self.save_section(
                geometry=geometry,
                frameless=True,
                clickthrough=True,
                toggled=True,
            )

            def finish_edit_mode():
                self.apply_config()
                # X11 frame extents remain stale briefly after decorations are
                # removed.  Re-anchor after the window manager has completed
                # that transition so the content does not visibly jump.
                def settle_saved_geometry():
                    saved = self.section()
                    values = list(saved.get("geometry") or geometry)
                    while len(values) < 4:
                        values.append(0)
                    x, y, width, height = [int(value) for value in values[:4]]
                    self.move_content_to(x, y)
                    self.window.resize(max(80, width), max(40, height))
                    self.set_click_through(True)
                    return False

                GLib.timeout_add(350, settle_saved_geometry)
                GLib.timeout_add(800, settle_saved_geometry)
                return False

            GLib.idle_add(finish_edit_mode)
            # Returning True prevents GTK from destroying the overlay and all
            # of its currently displayed rows/messages.
            return True

        def set_click_through(self, enabled):
            gdk_window = self.window.get_window()
            if not gdk_window:
                return
            try:
                gdk_window.set_pass_through(enabled)
            except Exception:
                pass
            try:
                # X11/Xfce may still route pointer events to a transparent GTK window
                # after set_pass_through().  Clearing the input shape makes the whole
                # overlay truly click-through.  Restore an explicit full-window region
                # because some X11 compositors do not reliably rebuild it from None.
                if enabled:
                    region = cairo.Region()
                else:
                    width, height = self.window.get_size()
                    width = max(1, int(width or self.window.get_allocated_width() or 1))
                    height = max(1, int(height or self.window.get_allocated_height() or 1))
                    region = cairo.Region(cairo.RectangleInt(0, 0, width, height))
                gdk_window.input_shape_combine_region(region, 0, 0)
            except Exception:
                pass

        def on_realize(self, *_args):
            section = self.section()
            self.set_click_through(
                bool(section.get("clickthrough", False)) or bool(section.get("lock_geometry", False))
            )

        def refresh_click_through(self):
            section = self.section()
            self.set_click_through(
                bool(section.get("clickthrough", False)) or bool(section.get("lock_geometry", False))
            )
            return False

        def on_map_event(self, *_args):
            section = self.section()
            self.set_click_through(
                bool(section.get("clickthrough", False)) or bool(section.get("lock_geometry", False))
            )
            GLib.idle_add(self.refresh_click_through)
            return False

        def on_size_allocate(self, _widget, allocation):
            # Timer overlays opt into compact descendant styles as their edit
            # frames narrow, while wrapped labels preserve the complete text.
            if self.section_name in ("spells", "nparse_spells"):
                compact = int(getattr(allocation, "width", 0) or 0) < 220
                context = self.content.get_style_context()
                if compact:
                    context.add_class("gina-compact")
                else:
                    context.remove_class("gina-compact")
                margin = 3 if compact else 8
                self.content.set_margin_top(margin)
                self.content.set_margin_bottom(margin)
                self.content.set_margin_start(margin)
                self.content.set_margin_end(margin)
            section = self.section()
            self.set_click_through(
                bool(section.get("clickthrough", False)) or bool(section.get("lock_geometry", False))
            )

        def on_button_press(self, _window, event):
            section = self.section()
            if (bool(section.get("lock_geometry", False))
                    or bool(section.get("clickthrough", False)) or event.button != 1):
                return False
            x, y = self.window.get_position()
            self.drag = {
                "pointer_x": int(event.x_root),
                "pointer_y": int(event.y_root),
                "window_x": x,
                "window_y": y,
            }
            return True

        def on_motion(self, _window, event):
            if not self.drag:
                return False
            new_x = self.drag["window_x"] + int(event.x_root) - self.drag["pointer_x"]
            new_y = self.drag["window_y"] + int(event.y_root) - self.drag["pointer_y"]
            self.window.move(new_x, new_y)
            return True

        def on_button_release(self, _window, event):
            if not self.drag or event.button != 1:
                return False
            self.drag = None
            section = self.section()
            if bool(section.get("lock_geometry", False)):
                return False
            geometry = list(section.get("geometry") or [0, 0, 300, 300])
            while len(geometry) < 4:
                geometry.append(0)
            current = self.current_content_geometry(geometry[2], geometry[3])
            geometry[0] = current[0]
            geometry[1] = current[1]
            geometry[2] = current[2]
            geometry[3] = current[3]
            self.save_section(geometry=geometry[:4])
            return True

        def on_scroll(self, _window, event):
            return False

        def apply_config(self):
            self.config_version = CONFIG_VERSION
            self.apply_window_frame()

        def tick(self):
            if not STATE["running"]:
                return False
            if self.config_version != CONFIG_VERSION:
                self.apply_config()
            return True

    class TextOverlay(BaseOverlay):
        section_name = "text_overlay"
        title = "EQ Watcher Text"

        def __init__(self):
            self.messages = []
            super().__init__()
            GLib.timeout_add(250, self.tick)

        def build_content(self):
            box = super().build_content()
            self.stack = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            box.pack_start(self.stack, True, True, 0)
            return box

        def apply_config(self):
            super().apply_config()
            section = self.section()
            css = f"""
                .gina-overlay-text-overlay {{
                    background-color: rgba(0, 0, 0, 0);
                    background-image: none;
                }}
                .gina-text-message {{
                    background-color: rgba(0, 0, 0, 0);
                    background-image: none;
                    border-radius: 4px;
                    padding: 10px 14px;
                }}
                .gina-text-label {{
                    color: #eef4fa;
                    font-weight: 900;
                    font-size: 28px;
                    text-shadow: 2px 2px 2px rgba(0,0,0,0.9);
                }}
            """
            self.css.load_from_data(css.encode("utf-8"))
            transparent = Gdk.RGBA()
            transparent.red = 0
            transparent.green = 0
            transparent.blue = 0
            transparent.alpha = 0
            self.window.override_background_color(Gtk.StateFlags.NORMAL, transparent)
            self.rebuild()
            self.set_click_through(bool(section.get("clickthrough", True)))
            self.update_visibility()

        def add_message(self, hit):
            section = self.section()
            show_all = bool(section.get("show_all_triggers", False))
            if not show_all and not bool(hit.get("use_text", False)):
                return
            text = str(hit.get("display_message") or hit.get("message") or "").strip()
            if not text:
                return
            seconds = max(1, min(30, int(section.get("duration_seconds", 4) or 4)))
            self.messages.insert(0, {
                "text": text,
                "color": hit.get("color", "#60a5fa"),
                "ends": time.time() + seconds,
            })
            self.messages = self.messages[:4]
            self.rebuild()
            self.update_visibility()

        def tick(self):
            while True:
                try:
                    hit = TEXT_OVERLAY_EVENTS.get_nowait()
                except queue.Empty:
                    break
                if bool(self.section().get("toggled", True)):
                    self.add_message(hit)
            now = time.time()
            before = len(self.messages)
            self.messages = [message for message in self.messages if message["ends"] > now]
            if before != len(self.messages):
                self.rebuild()
                self.update_visibility()
            if self.config_version != CONFIG_VERSION:
                self.apply_config()
            return True

        def update_visibility(self):
            section = self.section()
            visible = bool(section.get("toggled", True)) and (bool(self.messages) or not bool(section.get("frameless", True)))
            self.window.set_visible(visible)

        def rebuild(self):
            for child in list(self.stack.get_children()):
                self.stack.remove(child)
            for message in self.messages:
                row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
                row.get_style_context().add_class("gina-text-message")
                label = Gtk.Label(label=message["text"], xalign=0.5)
                label.get_style_context().add_class("gina-text-label")
                label.set_justify(Gtk.Justification.CENTER)
                label.set_line_wrap(True)
                label.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
                label.set_ellipsize(Pango.EllipsizeMode.END)
                row.pack_start(label, True, True, 0)
                self.stack.pack_start(row, False, False, 0)
            self.stack.show_all()
            self.update_visibility()

    class GinaOverlay(BaseOverlay):
        section_name = "spells"
        title = "EQ Watcher Timers"

        def __init__(self):
            self.timers = []
            super().__init__()
            GLib.timeout_add(1000, self.tick)

        def build_content(self):
            box = super().build_content()
            self.stack = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            box.pack_start(self.stack, True, True, 0)
            return box

        def apply_config(self):
            super().apply_config()
            section = self.section()
            opacity = max(0, min(100, int(section.get("opacity", 80)))) / 100
            css = f"""
                .gina-overlay-spells {{
                    background-color: rgba(0, 0, 0, {min(0.25, 0.95 - opacity * 0.7)});
                    background-image: none;
                }}
                .gina-row {{
                    background-color: rgba(0, 0, 0, {min(0.95, opacity)});
                    background-image: none;
                    border-radius: 2px;
                    padding: 8px;
                }}
                .gina-title {{ color: #f5d44f; font-weight: 800; font-size: 22px; }}
                .gina-time {{ color: #f5d44f; font-weight: 900; font-size: 34px; }}
                .gina-clear {{
                    min-width: 26px;
                    min-height: 26px;
                    padding: 0;
                    margin: 0;
                    font-size: 13px;
                    font-weight: 900;
                }}
                .gina-overlay-spells.gina-compact .gina-row {{
                    padding: 3px;
                }}
                .gina-overlay-spells.gina-compact .gina-title {{
                    font-size: 13px;
                }}
                .gina-overlay-spells.gina-compact .gina-time {{
                    font-size: 18px;
                }}
                .gina-overlay-spells.gina-compact .gina-clear {{
                    min-width: 18px;
                    min-height: 18px;
                    font-size: 10px;
                }}
            """
            self.css.load_from_data(css.encode("utf-8"))
            transparent = Gdk.RGBA()
            transparent.red = 0
            transparent.green = 0
            transparent.blue = 0
            transparent.alpha = 0
            self.window.override_background_color(Gtk.StateFlags.NORMAL, transparent)
            self.rebuild()
            self.set_click_through(
                bool(section.get("clickthrough", False)) or bool(section.get("lock_geometry", False))
            )

        def add_timer(self, hit):
            if timer_action(hit) == "stop":
                self.timers = remove_matching_timers(self.timers, hit)
                self.rebuild()
                return
            seconds = int(hit.get("timer_seconds") or 0)
            if seconds <= 0:
                return
            if hit.get("ignore_if_running", False) and any(
                timer.get("trigger_id") == hit.get("trigger_id") and timer.get("ends", 0) > time.time()
                for timer in self.timers
            ):
                return
            timer_id = str(hit.get("id") or hit.get("trigger_id") or uuid.uuid4().hex)
            if not hit.get("stack_timers", False):
                self.timers = [timer for timer in self.timers if timer["trigger_id"] != hit.get("trigger_id")]
            self.timers.append({
                "id": timer_id,
                "trigger_id": hit.get("trigger_id"),
                "name": hit.get("timer_name") or hit.get("message") or hit.get("name") or "Timer",
                "color": hit.get("color", "#60a5fa"),
                "ends": time.time() + seconds,
            })
            self.rebuild()

        def clear_timer(self, timer_id):
            timer_id = str(timer_id or "").strip()
            if not timer_id:
                return False
            before = len(self.timers)
            self.timers = [timer for timer in self.timers if str(timer.get("id", "")) != timer_id]
            if before != len(self.timers):
                self.rebuild()
                return True
            return False

        def tick(self):
            if not bool(self.section().get("toggled", False)):
                return True
            while True:
                try:
                    self.add_timer(GINA_OVERLAY_EVENTS.get_nowait())
                except queue.Empty:
                    break
            now = time.time()
            before = len(self.timers)
            self.timers = [timer for timer in self.timers if timer["ends"] > now]
            if before != len(self.timers):
                self.rebuild()
            if self.config_version != CONFIG_VERSION:
                self.apply_config()
            self.update_labels()
            return True

        def rebuild(self):
            for child in list(self.stack.get_children()):
                self.stack.remove(child)
            max_timers = 8
            self.timers.sort(key=lambda timer: timer["ends"])
            for timer in self.timers[:max_timers]:
                row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
                row.get_style_context().add_class("gina-row")
                strip = Gtk.EventBox()
                strip.set_size_request(7, 1)
                rgba = Gdk.RGBA()
                rgba.parse(timer["color"])
                strip.override_background_color(Gtk.StateFlags.NORMAL, rgba)
                title = Gtk.Label(label=timer["name"], xalign=0)
                title.get_style_context().add_class("gina-title")
                title.set_line_wrap(True)
                title.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
                title.set_ellipsize(Pango.EllipsizeMode.NONE)
                title.set_hexpand(True)
                label = Gtk.Label(label="00:00", xalign=1)
                label.get_style_context().add_class("gina-time")
                label.set_width_chars(5)
                clear_btn = None
                if bool(self.section().get("show_clear_buttons", False)):
                    clear_btn = Gtk.Button(label="X")
                    clear_btn.get_style_context().add_class("gina-clear")
                    clear_btn.set_tooltip_text("Clear timer")
                    clear_btn.connect("clicked", self.on_clear_timer, timer["id"])
                    clear_btn.set_size_request(26, 26)
                row.pack_start(strip, False, False, 0)
                row.pack_start(title, True, True, 0)
                row.pack_end(label, False, False, 0)
                if clear_btn is not None:
                    row.pack_end(clear_btn, False, False, 0)
                row.timer_label = label
                row.timer_data = timer
                self.stack.pack_start(row, False, False, 0)
            self.stack.show_all()
            self.update_labels()

        def on_clear_timer(self, _button, timer_id):
            self.clear_timer(timer_id)

        def update_labels(self):
            for row in self.stack.get_children():
                remaining = max(0, int(row.timer_data["ends"] - time.time() + 0.999))
                minutes, seconds = divmod(remaining, 60)
                row.timer_label.set_text(f"{minutes:02d}:{seconds:02d}")

    class NParseSpellsOverlay(BaseOverlay):
        section_name = "nparse_spells"
        title = "Spell Timers"

        def __init__(self):
            self.spells = []
            self.scout_payload = None
            self.scout_visible = False
            self.ring8_visible_timestamp = 0
            self.next_scout_refresh_at = 0.0
            super().__init__()
            GLib.timeout_add(1000, self.tick)

        @staticmethod
        def fetch_scout_timer():
            SCOUT_OVERLAY_EVENTS.put(scout_timer_payload())

        def refresh_scout_timer(self):
            now = time.monotonic()
            if now < self.next_scout_refresh_at:
                return
            self.next_scout_refresh_at = now + SCOUT_TIMER_CACHE_SECONDS
            threading.Thread(target=self.fetch_scout_timer, daemon=True).start()

        def build_content(self):
            box = super().build_content()
            self.title_label = Gtk.Label(xalign=0)
            self.title_label.get_style_context().add_class("gina-title")
            self.stack = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            box.pack_start(self.title_label, False, False, 0)
            box.pack_start(self.stack, True, True, 0)
            return box

        def apply_config(self):
            super().apply_config()
            section = self.section()
            opacity = max(0, min(100, int(section.get("opacity", 80)))) / 100
            css = f"""
                window.gina-window-nparse-spells,
                window.gina-window-nparse-spells.background,
                #gina-window-nparse-spells {{
                    background-color: transparent;
                    background-image: none;
                }}
                .gina-overlay-nparse-spells {{
                    background-color: transparent;
                    background-image: none;
                }}
                .gina-nparse-row {{
                    background-color: transparent;
                    background-image: none;
                    border: none;
                    padding: 2px 0;
                }}
                .gina-nparse-name {{ color: #eef4fa; font-weight: 700; font-size: 15px; }}
                .gina-nparse-time {{ color: #f5d44f; font-weight: 900; font-size: 20px; }}
                .gina-nparse-progress {{
                    min-height: 6px;
                }}
                .gina-nparse-progress trough {{
                    min-height: 6px;
                    background-color: rgba(238, 244, 250, 0.45);
                    background-image: none;
                    border: none;
                }}
                .gina-nparse-progress progress {{
                    min-height: 6px;
                    background-color: rgba(90, 167, 255, 0.95);
                    background-image: none;
                    border: none;
                }}
                .gina-overlay-nparse-spells.gina-compact .gina-nparse-row {{
                    padding: 1px 0;
                }}
                .gina-overlay-nparse-spells.gina-compact .gina-nparse-name {{
                    font-size: 12px;
                }}
                .gina-overlay-nparse-spells.gina-compact .gina-nparse-time {{
                    font-size: 15px;
                }}
                .gina-overlay-nparse-spells.gina-compact .gina-nparse-progress,
                .gina-overlay-nparse-spells.gina-compact .gina-nparse-progress trough,
                .gina-overlay-nparse-spells.gina-compact .gina-nparse-progress progress {{
                    min-height: 3px;
                }}
            """
            self.css.load_from_data(css.encode("utf-8"))
            transparent = Gdk.RGBA()
            transparent.red = 0
            transparent.green = 0
            transparent.blue = 0
            transparent.alpha = 0
            self.window.override_background_color(Gtk.StateFlags.NORMAL, transparent)
            self.rebuild()
            self.set_click_through(bool(section.get("clickthrough", False)))

        def add_spell(self, hit):
            if timer_action(hit) == "stop":
                self.spells = remove_matching_timers(self.spells, hit)
                self.rebuild()
                return
            seconds = int(hit.get("timer_seconds") or 0)
            if seconds <= 0:
                return
            if hit.get("ignore_if_running", False) and any(
                spell.get("spell_id") == hit.get("trigger_id") and spell.get("ends", 0) > time.time()
                for spell in self.spells
            ):
                return
            if hit.get("stack_timers", False):
                spell_id = hit.get("id") or uuid.uuid4().hex
            else:
                spell_id = hit.get("trigger_id") or hit.get("id") or hit.get("name") or uuid.uuid4().hex
                self.spells = [spell for spell in self.spells if spell["spell_id"] != spell_id]
            self.spells.append({
                "id": str(hit.get("id") or spell_id),
                "spell_id": spell_id,
                "name": hit.get("timer_name") or hit.get("message") or hit.get("name") or "Spell",
                "color": hit.get("color", "#60a5fa"),
                "ends": time.time() + seconds,
                "seconds": seconds,
            })
            self.rebuild()

        def clear_timer(self, timer_id, trigger_id=""):
            timer_id = str(timer_id or "").strip()
            trigger_id = str(trigger_id or "").strip()
            if not timer_id and not trigger_id:
                return False
            keys = {value for value in (timer_id, trigger_id) if value}
            before = len(self.spells)
            self.spells = [
                spell for spell in self.spells
                if keys.isdisjoint({str(spell.get("id", "")), str(spell.get("spell_id", ""))})
            ]
            if before != len(self.spells):
                self.rebuild()
                return True
            return False

        def clear_all_timers(self):
            self.spells = []
            self.rebuild()

        def tick(self):
            if not bool(self.section().get("toggled", False)):
                return True
            self.refresh_scout_timer()
            scout_changed = False
            while True:
                try:
                    self.scout_payload = SCOUT_OVERLAY_EVENTS.get_nowait()
                    scout_changed = True
                except queue.Empty:
                    break
            while True:
                try:
                    hit = NPARSE_SPELLS_EVENTS.get_nowait()
                    command = str(hit.get("overlay_command") or "")
                    if command == "clear_all":
                        self.clear_all_timers()
                    elif command == "clear_timer":
                        self.clear_timer(hit.get("id"), hit.get("trigger_id"))
                    else:
                        self.add_spell(hit)
                except queue.Empty:
                    break
            now = time.time()
            before = len(self.spells)
            self.spells = [spell for spell in self.spells if spell["ends"] > now]
            scout_visible = scout_overlay_timer(self.scout_payload, now) is not None
            ring8 = ring8_overlay_timer(now=now)
            ring8_visible_timestamp = float(ring8["ends"]) if ring8 is not None else 0
            if (
                scout_changed
                or before != len(self.spells)
                or scout_visible != self.scout_visible
                or ring8_visible_timestamp != self.ring8_visible_timestamp
            ):
                self.scout_visible = scout_visible
                self.ring8_visible_timestamp = ring8_visible_timestamp
                self.rebuild()
            if self.config_version != CONFIG_VERSION:
                self.apply_config()
            self.update_labels()
            return True

        def rebuild(self):
            for child in list(self.stack.get_children()):
                self.stack.remove(child)
            displayed_timers = list(self.spells)
            scout = scout_overlay_timer(self.scout_payload)
            if scout is not None:
                displayed_timers.append(scout)
            ring8 = ring8_overlay_timer()
            if ring8 is not None:
                displayed_timers.append(ring8)
            displayed_timers.sort(key=lambda spell: spell["ends"])
            for spell in displayed_timers:
                remaining = max(0, spell["ends"] - time.time())
                row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
                row.get_style_context().add_class("gina-nparse-row")
                head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
                strip = Gtk.EventBox()
                strip.set_size_request(7, 1)
                rgba = Gdk.RGBA()
                rgba.parse(spell["color"])
                strip.override_background_color(Gtk.StateFlags.NORMAL, rgba)
                title = Gtk.Label(label=spell["name"], xalign=0)
                title.get_style_context().add_class("gina-nparse-name")
                title.set_line_wrap(True)
                title.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
                title.set_ellipsize(Pango.EllipsizeMode.NONE)
                title.set_hexpand(True)
                time_label = Gtk.Label(label="00:00", xalign=1)
                time_label.get_style_context().add_class("gina-nparse-time")
                time_label.set_width_chars(5)
                head.pack_start(strip, False, False, 0)
                head.pack_start(title, True, True, 0)
                head.pack_end(time_label, False, False, 0)
                bar = Gtk.ProgressBar()
                bar.get_style_context().add_class("gina-nparse-progress")
                bar.set_show_text(False)
                bar.set_fraction(min(1.0, remaining / max(1.0, spell["seconds"])))
                row.pack_start(head, False, False, 0)
                row.pack_start(bar, False, False, 0)
                row.timer_label = time_label
                row.timer_bar = bar
                row.timer_data = spell
                self.stack.pack_start(row, False, False, 0)
            self.stack.show_all()
            self.update_labels()

        def update_labels(self):
            for row in self.stack.get_children():
                remaining = max(0, row.timer_data["ends"] - time.time())
                row.timer_label.set_text(f"{int(remaining // 60):02d}:{int(remaining % 60):02d}")
                row.timer_bar.set_fraction(min(1.0, remaining / max(1.0, row.timer_data["seconds"])))

    class RollOverlay(BaseOverlay):
        section_name = "rolls"
        title = "Roll Leaders"

        def __init__(self):
            self.contests = {}
            super().__init__()
            GLib.timeout_add(1000, self.tick)

        def build_content(self):
            box = super().build_content()
            title = Gtk.Label(label="Roll Leaders", xalign=0)
            title.get_style_context().add_class("gina-roll-title")
            self.stack = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            box.pack_start(title, False, False, 0)
            box.pack_start(self.stack, True, True, 0)
            return box

        def update_visibility(self):
            section = self.section()
            visible = bool(section.get("toggled", False)) and (
                bool(self.contests) or not bool(section.get("frameless", True))
            )
            self.window.set_visible(visible)

        def finish_initial_show(self):
            self.update_visibility()
            self.window.queue_draw()
            section = self.section()
            self.set_click_through(bool(section.get("clickthrough", True)))
            return False

        def apply_config(self):
            super().apply_config()
            opacity = max(0, min(100, int(self.section().get("opacity", 82)))) / 100
            css = f"""
                window.gina-window-rolls,
                window.gina-window-rolls.background,
                #gina-window-rolls {{
                    background-color: transparent;
                    background-image: none;
                }}
                .gina-overlay-rolls {{
                    background-color: rgba(3, 7, 12, {opacity * 0.72:.3f});
                    border: 1px solid rgba(245, 196, 66, 0.55);
                    border-radius: 5px;
                }}
                .gina-roll-title {{ color: #f5c442; font-weight: 900; font-size: 15px; }}
                .gina-roll-row {{
                    background-color: rgba(7, 12, 18, {opacity * 0.82:.3f});
                    border-left: 5px solid #f5c442;
                    padding: 5px 7px;
                }}
                .gina-roll-range {{ color: #a9bacb; font-weight: 700; font-size: 12px; }}
                .gina-roll-name {{ color: #f4f8fc; font-weight: 900; font-size: 17px; }}
                .gina-roll-score {{ color: #f5c442; font-weight: 900; font-size: 20px; }}
                .gina-roll-time {{ color: #8fd3ff; font-weight: 800; font-size: 13px; }}
            """
            self.css.load_from_data(css.encode("utf-8"))
            transparent = Gdk.RGBA()
            transparent.red = transparent.green = transparent.blue = transparent.alpha = 0
            self.window.override_background_color(Gtk.StateFlags.NORMAL, transparent)
            self.rebuild()
            self.set_click_through(bool(self.section().get("clickthrough", True)))
            self.update_visibility()

        def add_roll(self, roll):
            return update_roll_contests(self.contests, roll)

        def clear_all_rolls(self):
            self.contests = {}
            self.rebuild()
            self.update_visibility()

        def tick(self):
            changed = False
            while True:
                try:
                    roll = ROLL_OVERLAY_EVENTS.get_nowait()
                    if str(roll.get("overlay_command") or "") == "clear_all":
                        self.clear_all_rolls()
                    else:
                        self.add_roll(roll)
                    changed = True
                except queue.Empty:
                    break
            now = time.time()
            active = {
                key: contest for key, contest in self.contests.items()
                if float(contest.get("expires_at") or 0) > now
            }
            if len(active) != len(self.contests):
                self.contests = active
                changed = True
            if changed:
                self.rebuild()
            if self.config_version != CONFIG_VERSION:
                self.apply_config()
            self.update_labels()
            self.update_visibility()
            return True

        def rebuild(self):
            for child in list(self.stack.get_children()):
                self.stack.remove(child)
            for key in sorted(self.contests):
                contest = self.contests[key]
                row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
                row.get_style_context().add_class("gina-roll-row")
                top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
                range_label = Gtk.Label(label=f"{key[0]}–{key[1]}", xalign=0)
                range_label.get_style_context().add_class("gina-roll-range")
                time_label = Gtk.Label(label="05:00", xalign=1)
                time_label.get_style_context().add_class("gina-roll-time")
                top.pack_start(range_label, True, True, 0)
                top.pack_end(time_label, False, False, 0)
                leader = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
                name = Gtk.Label(label=str(contest.get("name") or "Unknown"), xalign=0)
                name.get_style_context().add_class("gina-roll-name")
                name.set_ellipsize(Pango.EllipsizeMode.END)
                score = Gtk.Label(label=str(contest.get("value", 0)), xalign=1)
                score.get_style_context().add_class("gina-roll-score")
                leader.pack_start(name, True, True, 0)
                leader.pack_end(score, False, False, 0)
                row.pack_start(top, False, False, 0)
                row.pack_start(leader, False, False, 0)
                row.timer_label = time_label
                row.timer_data = contest
                self.stack.pack_start(row, False, False, 0)
            self.stack.show_all()
            self.update_labels()

        def update_labels(self):
            for row in self.stack.get_children():
                remaining = max(0, int(row.timer_data["expires_at"] - time.time() + 0.999))
                minutes, seconds = divmod(remaining, 60)
                row.timer_label.set_text(f"{minutes:02d}:{seconds:02d}")

    class DPSOverlay(BaseOverlay):
        section_name = "dps"
        title = "EQ Watcher DPS"

        def __init__(self):
            self.payload = dps_payload()
            self.cycle_encounter_id = ""
            self.last_cycle_ts = 0
            super().__init__()
            GLib.timeout_add(500, self.tick)

        def build_content(self):
            box = super().build_content()
            # The DPS meter is often kept beside the game at a glance.  Use
            # smaller outer margins than the timer overlays so GTK does not
            # reserve unnecessary space when the window is resized compactly.
            box.set_margin_top(3)
            box.set_margin_bottom(3)
            box.set_margin_start(3)
            box.set_margin_end(3)
            self.header = Gtk.Label(label="DPS Parse", xalign=0)
            self.header.get_style_context().add_class("gina-dps-header")
            self.header.set_ellipsize(Pango.EllipsizeMode.END)
            self.summary = Gtk.Label(label="No target", xalign=0)
            self.summary.get_style_context().add_class("gina-dps-summary")
            self.summary.set_ellipsize(Pango.EllipsizeMode.END)
            self.stack = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
            self.stack_view = Gtk.ScrolledWindow()
            self.stack_view.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.NEVER)
            self.stack_view.set_propagate_natural_width(False)
            self.stack_view.set_propagate_natural_height(False)
            self.stack_view.set_min_content_width(120)
            self.stack_view.set_min_content_height(24)
            self.stack_view.add(self.stack)
            self.proc_stack = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            box.pack_start(self.header, False, False, 0)
            box.pack_start(self.summary, False, False, 0)
            box.pack_start(self.stack_view, True, True, 0)
            box.pack_start(self.proc_stack, False, False, 0)
            return box

        def apply_config(self):
            super().apply_config()
            section = self.section()
            opacity = max(0, min(100, int(section.get("opacity", 72)))) / 100
            css = f"""
                window.gina-window-dps,
                window.gina-window-dps.background,
                #gina-window-dps {{
                    background-color: transparent;
                    background-image: none;
                }}
                .gina-overlay-dps {{
                    background-color: rgba(0, 0, 0, {min(0.88, opacity)});
                    background-image: none;
                    border-radius: 4px;
                    padding: 4px;
                }}
                .gina-dps-header {{
                    color: #f5d44f;
                    font-weight: 900;
                    font-size: 16px;
                }}
                .gina-dps-summary {{
                    color: #cbd5e1;
                    font-size: 11px;
                    padding-bottom: 2px;
                }}
                .gina-dps-row {{
                    background-color: rgba(255, 255, 255, 0.04);
                    background-image: none;
                    border-radius: 2px;
                    padding: 2px 3px;
                }}
                .gina-dps-rank {{ color: #9aa7b2; font-size: 11px; }}
                .gina-dps-name {{ color: #eef4fa; font-weight: 800; font-size: 12px; }}
                .gina-dps-value {{ color: #f5d44f; font-weight: 900; font-size: 12px; }}
                .gina-dps-meta {{ color: #9aa7b2; font-size: 10px; }}
                .gina-dps-proc {{ color: #dbeafe; font-weight: 700; font-size: 11px; }}
                .gina-dps-proc-land {{ color: #86efac; font-weight: 800; font-size: 11px; }}
                .gina-dps-proc-resist {{ color: #fca5a5; font-weight: 800; font-size: 11px; }}
            """
            self.css.load_from_data(css.encode("utf-8"))
            transparent = Gdk.RGBA()
            transparent.red = 0
            transparent.green = 0
            transparent.blue = 0
            transparent.alpha = 0
            self.window.override_background_color(Gtk.StateFlags.NORMAL, transparent)
            self.rebuild()
            self.set_click_through(
                bool(section.get("clickthrough", False)) or bool(section.get("lock_geometry", False))
            )

        def tick(self):
            if not STATE["running"]:
                return False
            updated = False
            while True:
                try:
                    DPS_EVENTS.get_nowait()
                    updated = True
                except queue.Empty:
                    break
            section = self.section()
            if bool(section.get("cycle_enabled", False)):
                cycle_seconds = max(2, int(section.get("cycle_seconds", 8) or 8))
                now = time.time()
                base_payload = dps_payload(encounter_id=self.cycle_encounter_id)
                encounters = list(base_payload.get("encounters") or [])
                ids = [item.get("encounter_id", "") for item in encounters if item.get("encounter_id")]
                if ids and (not self.cycle_encounter_id or now - self.last_cycle_ts >= cycle_seconds):
                    index = ids.index(self.cycle_encounter_id) if self.cycle_encounter_id in ids else -1
                    self.cycle_encounter_id = ids[(index + 1) % len(ids)]
                    self.last_cycle_ts = now
                self.payload = dps_payload(encounter_id=self.cycle_encounter_id)
                updated = True
            elif updated:
                self.cycle_encounter_id = ""
                self.payload = dps_payload()
            if self.config_version != CONFIG_VERSION:
                if not bool(self.section().get("cycle_enabled", False)):
                    self.payload = dps_payload()
                self.apply_config()
                updated = False
            if updated:
                self.rebuild()
            return True

        def rebuild(self):
            for child in list(self.stack.get_children()):
                self.stack.remove(child)
            for child in list(self.proc_stack.get_children()):
                self.proc_stack.remove(child)
            payload = self.payload or dps_payload()
            target = payload.get("target") or "No target"
            duration = int(payload.get("duration") or 0)
            total_damage = int(payload.get("total_damage") or 0)
            total_dps = float(payload.get("total_dps") or 0)
            status = "live" if payload.get("active") else "ended"
            if not payload.get("target"):
                status = "idle"
            self.header.set_text(target)
            self.summary.set_text(f"{status}  {duration // 60:02d}:{duration % 60:02d}  {total_damage:,} dmg  {total_dps:.2f} raid DPS")
            rows = list(payload.get("rows") or [])
            max_rows = max(1, int(self.section().get("max_rows", 10) or 10))
            for index, row_data in enumerate(rows[:max_rows], start=1):
                row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=3)
                row.get_style_context().add_class("gina-dps-row")
                rank = Gtk.Label(label=f"{index:>2}", xalign=1)
                rank.get_style_context().add_class("gina-dps-rank")
                rank.set_width_chars(2)
                name = Gtk.Label(label=str(row_data.get("name") or ""), xalign=0)
                name.get_style_context().add_class("gina-dps-name")
                name.set_ellipsize(Pango.EllipsizeMode.END)
                dps = Gtk.Label(label=f"{float(row_data.get('dps') or 0):.2f}", xalign=1)
                dps.get_style_context().add_class("gina-dps-value")
                dps.set_width_chars(6)
                damage = Gtk.Label(label=f"{int(row_data.get('damage') or 0):,}", xalign=1)
                damage.get_style_context().add_class("gina-dps-meta")
                damage.set_width_chars(7)
                row.pack_start(rank, False, False, 0)
                row.pack_start(name, True, True, 0)
                row.pack_end(dps, False, False, 0)
                row.pack_end(damage, False, False, 0)
                self.stack.pack_start(row, False, False, 0)
            if not rows:
                empty = Gtk.Label(label="Waiting for outgoing damage.", xalign=0)
                empty.get_style_context().add_class("gina-dps-meta")
                self.stack.pack_start(empty, False, False, 0)
            proc_counts = payload.get("proc_counts") or {}
            for weapon, label in (("willsapper", "Willsapper"), ("blade of strategy", "Blade of Strategy")):
                counts = proc_counts.get(weapon) or {}
                proc_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
                name = Gtk.Label(label=label, xalign=0)
                name.get_style_context().add_class("gina-dps-proc")
                name.set_ellipsize(Pango.EllipsizeMode.END)
                landed = Gtk.Label(label=f"Land {int(counts.get('landed', 0))}", xalign=1)
                landed.get_style_context().add_class("gina-dps-proc-land")
                resisted = Gtk.Label(label=f"Resist {int(counts.get('resisted', 0))}", xalign=1)
                resisted.get_style_context().add_class("gina-dps-proc-resist")
                proc_row.pack_start(name, True, True, 0)
                proc_row.pack_end(resisted, False, False, 0)
                proc_row.pack_end(landed, False, False, 0)
                self.proc_stack.pack_start(proc_row, False, False, 0)
            self.stack.show_all()
            self.proc_stack.show_all()

    class AggroOverlay(BaseOverlay):
        section_name = "aggro"
        title = "EQ Watcher Aggro"

        def __init__(self):
            self.payload = aggro_payload()
            super().__init__()
            GLib.timeout_add(500, self.tick)

        def build_content(self):
            box = super().build_content()
            self.header = Gtk.Label(label="Aggro Meter", xalign=0)
            self.header.get_style_context().add_class("gina-aggro-header")
            self.header.set_ellipsize(Pango.EllipsizeMode.END)
            self.summary = Gtk.Label(label="Estimated · waiting for your attack", xalign=0)
            self.summary.get_style_context().add_class("gina-aggro-summary")
            self.summary.set_line_wrap(False)
            self.summary.set_single_line_mode(True)
            self.summary.set_ellipsize(Pango.EllipsizeMode.END)
            self.stack = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
            # Keep row count and label width from changing the window's natural
            # height during a horizontal edge resize.  Overflow is clipped just
            # like the compact DPS meter.
            self.stack_view = Gtk.ScrolledWindow()
            self.stack_view.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.NEVER)
            self.stack_view.set_propagate_natural_width(False)
            self.stack_view.set_propagate_natural_height(False)
            self.stack_view.set_min_content_width(140)
            self.stack_view.set_min_content_height(24)
            self.stack_view.add(self.stack)
            box.pack_start(self.header, False, False, 0)
            box.pack_start(self.summary, False, False, 0)
            box.pack_start(self.stack_view, True, True, 0)
            return box

        def apply_config(self):
            super().apply_config()
            opacity = max(0, min(100, int(self.section().get("opacity", 76)))) / 100
            css = f"""
                window.gina-window-aggro,
                window.gina-window-aggro.background,
                #gina-window-aggro {{ background-color: transparent; background-image: none; }}
                .gina-overlay-aggro {{
                    background-color: rgba(0, 0, 0, {min(0.9, opacity)});
                    background-image: none; border-radius: 4px; padding: 8px;
                }}
                .gina-aggro-header {{ color: #ff9f43; font-weight: 900; font-size: 18px; }}
                .gina-aggro-summary {{ color: #cbd5e1; font-size: 11px; padding-bottom: 4px; }}
                .gina-aggro-row {{ background-color: rgba(255,255,255,0.04); padding: 4px 6px; }}
                .gina-aggro-self {{ background-color: rgba(245,158,11,0.18); }}
                .gina-aggro-rank {{ color: #9aa7b2; font-size: 11px; }}
                .gina-aggro-name {{ color: #eef4fa; font-weight: 800; font-size: 13px; }}
                .gina-aggro-value {{ color: #ffb454; font-weight: 900; font-size: 13px; }}
                .gina-aggro-meta {{ color: #9aa7b2; font-size: 10px; }}
            """
            self.css.load_from_data(css.encode("utf-8"))
            transparent = Gdk.RGBA()
            transparent.red = transparent.green = transparent.blue = transparent.alpha = 0
            self.window.override_background_color(Gtk.StateFlags.NORMAL, transparent)
            self.rebuild()
            self.set_click_through(bool(self.section().get("clickthrough", True)))

        def tick(self):
            if not STATE["running"]:
                return False
            updated = False
            while True:
                try:
                    self.payload = AGGRO_EVENTS.get_nowait()
                    updated = True
                except queue.Empty:
                    break
            if self.config_version != CONFIG_VERSION:
                self.apply_config()
                updated = False
            if updated:
                self.rebuild()
            return True

        def rebuild(self):
            for child in list(self.stack.get_children()):
                self.stack.remove(child)
            payload = self.payload or aggro_payload()
            target = payload.get("target") or "Aggro Meter"
            status = "live" if payload.get("active") else "idle"
            duration = int(payload.get("duration") or 0)
            inventory = payload.get("inventory") or {}
            primary = inventory.get("primary") or "unknown"
            secondary = inventory.get("secondary") or "empty"
            self.header.set_text(target)
            summary_text = (
                f"Estimated · {status} · {duration // 60:02d}:{duration % 60:02d} · "
                f"Flux = threat ÷ 50 · You: {primary} / {secondary}"
            )
            self.summary.set_text(summary_text)
            self.summary.set_tooltip_text(summary_text)
            rows = list(payload.get("rows") or [])
            max_rows = max(1, int(self.section().get("max_rows", 8) or 8))
            for index, row_data in enumerate(rows[:max_rows], start=1):
                row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
                row.get_style_context().add_class("gina-aggro-row")
                if row_data.get("is_self"):
                    row.get_style_context().add_class("gina-aggro-self")
                rank = Gtk.Label(label=f"{index:>2}", xalign=1)
                rank.get_style_context().add_class("gina-aggro-rank")
                rank.set_width_chars(2)
                player_name = str(row_data.get("name") or "")
                player_class = str(row_data.get("class") or "")
                name = Gtk.Label(label=f"{player_name} · {player_class}" if player_class else player_name, xalign=0)
                name.get_style_context().add_class("gina-aggro-name")
                name.set_ellipsize(Pango.EllipsizeMode.END)
                threat = float(row_data.get("threat") or 0)
                threat_text = f"{threat / 1000:.1f}k" if threat >= 1000 else f"{threat:.0f}"
                value = Gtk.Label(label=threat_text, xalign=1)
                value.get_style_context().add_class("gina-aggro-value")
                value.set_width_chars(6)
                proc_count = int(row_data.get("procs") or 0)
                meta_text = f"{float(row_data.get('percent') or 0):.0f}% F{int(row_data.get('flux') or 0)}"
                if proc_count:
                    meta_text += f" P{proc_count}"
                meta = Gtk.Label(label=meta_text, xalign=1)
                meta.get_style_context().add_class("gina-aggro-meta")
                meta.set_width_chars(10)
                row.pack_start(rank, False, False, 0)
                row.pack_start(name, True, True, 0)
                row.pack_end(value, False, False, 0)
                row.pack_end(meta, False, False, 0)
                self.stack.pack_start(row, False, False, 0)
            if not rows:
                empty = Gtk.Label(label="Waiting for your outgoing attack.", xalign=0)
                empty.get_style_context().add_class("gina-aggro-meta")
                self.stack.pack_start(empty, False, False, 0)
            self.stack.show_all()

    class MapsOverlay(BaseOverlay):
        section_name = "maps"
        title = "EQ Watcher Maps"

        def __init__(self):
            self.zoom = 1.0
            self.last_render_key = None
            super().__init__()
            GLib.timeout_add(1000, self.tick)

        def build_content(self):
            box = super().build_content()
            self.title_label = Gtk.Label(xalign=0)
            self.title_label.get_style_context().add_class("gina-title")
            self.map_event_box = Gtk.EventBox()
            self.map_event_box.set_visible_window(False)
            self.map_event_box.add_events(Gdk.EventMask.SCROLL_MASK)
            self.map_event_box.connect("scroll-event", self.on_scroll)
            self.map_image = Gtk.Image()
            self.map_image.set_size_request(260, 200)
            self.map_event_box.add(self.map_image)
            self.footer = Gtk.Label(xalign=0)
            self.footer.set_line_wrap(True)
            box.pack_start(self.title_label, False, False, 0)
            box.pack_start(self.map_event_box, True, True, 0)
            box.pack_start(self.footer, False, False, 0)
            return box

        def on_scroll(self, _window, event):
            section = self.section()
            direction = 0
            if event.direction == Gdk.ScrollDirection.SMOOTH:
                try:
                    deltas = event.get_scroll_deltas()
                    if len(deltas) == 3:
                        _ok, _dx, dy = deltas
                    else:
                        _dx, dy = deltas
                    direction = -1 if dy > 0 else 1 if dy < 0 else 0
                except Exception:
                    direction = 0
            elif event.direction == Gdk.ScrollDirection.DOWN:
                direction = -1
            elif event.direction == Gdk.ScrollDirection.UP:
                direction = 1
            if direction == 0:
                return False
            scale = float(section.get("scale", 0.01947098754708777) or 0.01947098754708777)
            scale = max(0.0002, min(1.0, scale * (1.35 if direction > 0 else 1 / 1.35)))
            self.save_section(scale=scale)
            self.apply_config()
            return True

        def hex_to_rgba(self, color, opacity):
            text = str(color or "#000000").strip().lstrip("#")
            if len(text) == 6:
                r = int(text[0:2], 16)
                g = int(text[2:4], 16)
                b = int(text[4:6], 16)
            else:
                r, g, b = 0, 0, 0
            return (r, g, b, int(max(0.0, min(1.0, opacity)) * 255))

        def boost_color(self, color, floor=145, blend=0.28):
            r, g, b = [max(0, min(255, int(value))) for value in color[:3]]
            r = int(max(floor, r + (255 - r) * blend))
            g = int(max(floor, g + (255 - g) * blend))
            b = int(max(floor, b + (255 - b) * blend))
            return r, g, b

        def draw_readable_text(self, draw, position, text, fill):
            x, y = position
            shadow = (0, 0, 0, 230)
            for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                draw.text((x + dx, y + dy), text, fill=shadow)
            draw.text((x, y), text, fill=fill)

        def apply_config(self):
            super().apply_config()
            section = self.section()
            bg_opacity = max(0, min(100, int(section.get("opacity", 80)))) / 100
            css = f"""
                .gina-overlay-maps {{
                    background-color: rgba(0, 0, 0, {max(0.05, 1.0 - bg_opacity)});
                    background-image: none;
                }}
            """
            self.css.load_from_data(css.encode("utf-8"))
            self.set_click_through(bool(section.get("clickthrough", False)))
            self.update_labels()
            self.render_map_image()
            self.update_visibility()

        def update_visibility(self):
            self.window.set_visible(should_show_maps_overlay(self.section()))

        def finish_initial_show(self):
            self.update_visibility()
            self.window.queue_draw()
            self.set_click_through(bool(self.section().get("clickthrough", False)))
            return False

        def render_map_image(self):
            from io import BytesIO
            from PIL import Image, ImageDraw, ImageFont
            from gi.repository import GdkPixbuf

            section = self.section()
            zone = current_nparse_zone_name()
            zone_label, zone_key = resolve_nparse_zone(zone)
            zone_record = current_nparse_zone_record()
            alloc = self.map_event_box.get_allocation()
            width = max(260, alloc.width or 260)
            height = max(200, alloc.height or 200)
            render_key = (
                zone_key,
                width,
                height,
                STATE.get("location_x"),
                STATE.get("location_y"),
                STATE.get("location_z"),
                STATE.get("heading"),
                STATE.get("movement_angle"),
                bool(section.get("center_character_location", False)),
                bool(section.get("show_grid", True)),
                bool(section.get("show_poi", True)),
                int(section.get("opacity", 80)),
                str(section.get("color", "#000000") or "#000000"),
                float(section.get("scale", 0.01947098754708777) or 0.01947098754708777),
                int(section.get("line_width", 1) or 1),
                int(section.get("grid_line_width", 1) or 1),
            )
            if render_key == self.last_render_key:
                return
            self.last_render_key = render_key
            bg_color = section.get("color", "#000000") or "#000000"
            opacity = max(0, min(100, int(section.get("opacity", 80)))) / 100.0
            image = Image.new("RGBA", (width, height), self.hex_to_rgba(bg_color, max(opacity, 0.92)))
            draw = ImageDraw.Draw(image)
            lines = zone_record.get("lines", [])
            points = zone_record.get("points", [])
            bounds = zone_record.get("bounds", {})
            location_x = STATE.get("location_x")
            location_y = STATE.get("location_y")
            center_character = bool(section.get("center_character_location", False))
            if not lines and not points:
                draw.text((10, 12), "No map data for this zone", fill=(255, 255, 255, 200))
            else:
                min_x = float(bounds.get("min_x", 0.0))
                min_y = float(bounds.get("min_y", 0.0))
                max_x = float(bounds.get("max_x", 1.0))
                max_y = float(bounds.get("max_y", 1.0))
                pad = max(8.0, max(max_x - min_x, max_y - min_y) * 0.05)
                min_x -= pad
                min_y -= pad
                max_x += pad
                max_y += pad
                map_w = max(1.0, max_x - min_x)
                map_h = max(1.0, max_y - min_y)
                scale = min(width / map_w, height / map_h) * float(section.get("scale", 0.01947098754708777) or 0.01947098754708777) * 28.0
                scale = max(0.005, min(30.0, scale))
                use_center = center_character and location_x is not None and location_y is not None
                if use_center:
                    marker_x = float(location_x)
                    marker_y = float(location_y)
                    offset_x = (width / 2.0) - (marker_x * scale)
                    offset_y = (height / 2.0) - (marker_y * scale)
                    view_min_x = (0.0 - offset_x) / scale
                    view_min_y = (0.0 - offset_y) / scale
                    view_max_x = (width - offset_x) / scale
                    view_max_y = (height - offset_y) / scale
                else:
                    offset_x = (width - map_w * scale) / 2.0
                    offset_y = (height - map_h * scale) / 2.0
                    view_min_x = min_x
                    view_min_y = min_y
                    view_max_x = max_x
                    view_max_y = max_y

                def tx(x):
                    if use_center:
                        return int(offset_x + (x * scale))
                    return int(offset_x + (x - min_x) * scale)

                def ty(y):
                    if use_center:
                        return int(offset_y + (y * scale))
                    return int(offset_y + (y - min_y) * scale)

                if section.get("show_grid", True):
                    grid_color = (120, 190, 255, 75)
                    step = 100.0
                    x = math.floor(view_min_x / step) * step
                    while x <= view_max_x:
                        draw.line((tx(x), ty(view_min_y), tx(x), ty(view_max_y)), fill=grid_color, width=max(1, int(section.get("grid_line_width", 1) or 1)))
                        x += step
                    y = math.floor(view_min_y / step) * step
                    while y <= view_max_y:
                        draw.line((tx(view_min_x), ty(y), tx(view_max_x), ty(y)), fill=grid_color, width=max(1, int(section.get("grid_line_width", 1) or 1)))
                        y += step
                for line in lines:
                    color = self.boost_color(tuple(line.get("color") or [255, 255, 255]))
                    line_width = max(1, int(section.get("line_width", 1) or 1))
                    coords = (tx(line["x1"]), ty(line["y1"]), tx(line["x2"]), ty(line["y2"]))
                    draw.line(coords, fill=(0, 0, 0, 180), width=line_width + 2)
                    draw.line(
                        coords,
                        fill=(color[0], color[1], color[2], 255),
                        width=line_width,
                    )
                if section.get("show_poi", True):
                    for point in points:
                        color = self.boost_color(tuple(point.get("color") or [255, 255, 255]), floor=165, blend=0.35)
                        size = max(2, min(6, int(point.get("size", 3) or 3)))
                        x = tx(point["x"])
                        y = ty(point["y"])
                        draw.ellipse((x - size - 1, y - size - 1, x + size + 1, y + size + 1), fill=(0, 0, 0, 220))
                        draw.ellipse((x - size, y - size, x + size, y + size), fill=(color[0], color[1], color[2], 255))
                        label = point.get("label", "")
                        if label:
                            self.draw_readable_text(draw, (x + 5, y - 7), label, (245, 250, 255, 255))
                if location_x is not None and location_y is not None:
                    marker_x = float(location_x)
                    marker_y = float(location_y)
                    px = tx(marker_x)
                    py = ty(marker_y)
                    if not use_center:
                        px = max(8, min(width - 8, px))
                        py = max(8, min(height - 8, py))
                    heading = str(STATE.get("heading", "") or "").strip()
                    movement_angle = STATE.get("movement_angle")
                    bearing = heading_to_bearing(heading)
                    marker_color = (255, 224, 54, 255)
                    outline_color = (0, 0, 0, 245)
                    if movement_angle is not None or bearing is not None:
                        angle = float(movement_angle) if movement_angle is not None else math.radians(bearing - 90.0)
                        size = 13.0
                        tail = 8.0
                        half_width = 6.0
                        tip = (px + math.cos(angle) * size, py + math.sin(angle) * size)
                        back = (px - math.cos(angle) * tail, py - math.sin(angle) * tail)
                        left = (
                            back[0] + math.cos(angle - math.pi / 2.0) * half_width,
                            back[1] + math.sin(angle - math.pi / 2.0) * half_width,
                        )
                        right = (
                            back[0] + math.cos(angle + math.pi / 2.0) * half_width,
                            back[1] + math.sin(angle + math.pi / 2.0) * half_width,
                        )
                        draw.polygon((tip, left, right), fill=marker_color)
                        draw.line((tip, left, right, tip), fill=outline_color, width=3)
                        draw.ellipse((px - 2, py - 2, px + 2, py + 2), fill=outline_color)
                    else:
                        draw.ellipse((px - 8, py - 8, px + 8, py + 8), outline=outline_color, width=5)
                        draw.ellipse((px - 7, py - 7, px + 7, py + 7), outline=marker_color, width=3)
                        draw.ellipse((px - 2, py - 2, px + 2, py + 2), fill=marker_color)
                    label = "YOU"
                    if heading:
                        label = f"YOU {heading}"
                    if not use_center and (marker_x < min_x or marker_x > max_x or marker_y < min_y or marker_y > max_y):
                        label += " (off-map)"
                    self.draw_readable_text(draw, (px + 8, py - 10), label, (255, 224, 54, 255))
                self.draw_readable_text(draw, (8, 8), zone_label or zone or "Map", (255, 224, 54, 255))

            buf = BytesIO()
            image.save(buf, format="PNG")
            loader = GdkPixbuf.PixbufLoader.new_with_type("png")
            loader.write(buf.getvalue())
            loader.close()
            pixbuf = loader.get_pixbuf()
            self.map_image.set_from_pixbuf(pixbuf)

        def update_labels(self):
            zone = current_nparse_zone_name()
            zone_label, zone_key = resolve_nparse_zone(zone)
            timer = current_nparse_zone_timer()
            label = zone_label or zone or "No zone selected"
            if zone_key and normalize_nparse_key(zone_key) != normalize_nparse_key(label):
                label = f"{label} · {zone_key}"
            self.title_label.set_text(label)
            pieces = []
            if timer and timer.get("duration_text"):
                pieces.append(f"Zone respawn {timer['duration_text']}")
            if STATE.get("location_x") is not None and STATE.get("location_y") is not None:
                pieces.append(
                    f"YOU {STATE.get('location_x'):.2f}, {STATE.get('location_y'):.2f}, {STATE.get('location_z'):.2f}"
                    if STATE.get("location_z") is not None
                    else f"YOU {STATE.get('location_x'):.2f}, {STATE.get('location_y'):.2f}"
                )
            self.footer.set_text("  ".join(pieces))

        def tick(self):
            section = self.section()
            self.window.set_visible(should_show_maps_overlay(section))
            if not bool(section.get("toggled", False)):
                return True
            if self.config_version != CONFIG_VERSION:
                self.apply_config()
            self.update_labels()
            self.render_map_image()
            return True

    class DiscordOverlay(BaseOverlay):
        section_name = "discord"
        title = "EQ Watcher Discord"

        def __init__(self):
            super().__init__()
            GLib.timeout_add(1000, self.tick)

        def build_content(self):
            box = super().build_content()
            self.title_label = Gtk.Label(xalign=0)
            self.title_label.get_style_context().add_class("gina-title")
            self.info = Gtk.Label(xalign=0)
            self.info.set_line_wrap(True)
            box.pack_start(self.title_label, False, False, 0)
            box.pack_start(self.info, True, True, 0)
            return box

        def apply_config(self):
            super().apply_config()
            section = self.section()
            bg_opacity = max(0, min(100, int(section.get("bg_opacity", 25)))) / 100
            css = f"""
                .gina-overlay-discord {{
                    background-color: rgba(0, 0, 0, {bg_opacity});
                    background-image: none;
                }}
            """
            self.css.load_from_data(css.encode("utf-8"))
            self.set_click_through(bool(section.get("clickthrough", False)))
            self.update_labels()

        def update_labels(self):
            section = self.section()
            player = section.get("player_name") or STATE.get("character", "") or "Unknown"
            group_key = section.get("group_key") or "public"
            url = section.get("url") or "ws://sheeplauncher.net:8424"
            status = "enabled" if bool(section.get("enabled", False)) else "disabled"
            zone = current_nparse_zone_name() or "No zone"
            self.title_label.set_text("Discord")
            self.info.set_text(
                f"Player: {player}\n"
                f"Group: {group_key}\n"
                f"Status: {status}\n"
                f"Zone: {zone}\n"
                f"URL: {url}"
            )

        def tick(self):
            if not bool(self.section().get("toggled", False)):
                return True
            if self.config_version != CONFIG_VERSION:
                self.apply_config()
            self.update_labels()
            return True

    class CHChainOverlay(BaseOverlay):
        section_name = "ch_chain"
        title = "EQ Watcher CH Chain"

        def __init__(self):
            self.chains = {}
            self.latest_key = None
            super().__init__()
            GLib.timeout_add(250, self.tick)

        def build_content(self):
            box = super().build_content()
            self.area = Gtk.DrawingArea()
            self.area.set_size_request(640, 64)
            self.area.connect("draw", self.on_chain_draw)
            box.pack_start(self.area, True, True, 0)
            return box

        def apply_config(self):
            super().apply_config()
            section = self.section()
            opacity = max(0, min(100, int(section.get("opacity", 18)))) / 100
            css = f"""
                .gina-overlay-ch-chain {{
                    background-color: rgba(0, 0, 0, 0);
                    background-image: none;
                }}
            """
            self.css.load_from_data(css.encode("utf-8"))
            self.set_click_through(bool(section.get("clickthrough", False)))
            self.area.queue_draw()

        def chain_key(self, hit):
            tag = str(hit.get("tag") or "").upper()
            target = normalize_timer_key(hit.get("target") or "Unknown")
            return f"{tag}|{target}"

        def add_chain_hit(self, hit):
            section = self.section()
            tag_filter = str(section.get("tag_filter") or "").strip().upper()
            tag = str(hit.get("tag") or "").strip().upper()
            if tag_filter and tag != tag_filter:
                return
            key = self.chain_key(hit)
            chain = self.chains.setdefault(key, {
                "tag": tag,
                "target": str(hit.get("target") or "Unknown").strip() or "Unknown",
                "positions": {},
                "metronome_started": time.time(),
                "updated": 0,
                "latest": "",
                "latest_id": "",
            })
            display = str(hit.get("display") or hit.get("position") or "").strip().upper()
            if not display:
                return
            cast_id = str(hit.get("id") or uuid.uuid4())
            chain["tag"] = tag
            chain["target"] = str(hit.get("target") or chain.get("target") or "Unknown").strip() or "Unknown"
            chain["positions"][cast_id] = {
                "id": cast_id,
                "display": display,
                "sort": int(hit.get("sort") or 0),
                "ramp": bool(hit.get("ramp")),
                "ramp_display": str(hit.get("ramp_display") or display).strip().upper(),
                "time": float(hit.get("time") or time.time()),
                "line": hit.get("line", ""),
            }
            chain["updated"] = time.time()
            chain["latest"] = display
            chain["latest_id"] = cast_id
            self.latest_key = key
            self.area.queue_draw()

        def active_chain(self):
            now = time.time()
            section = self.section()
            ttl = max(30, int(section.get("ttl_seconds", 900) or 900))
            active_seconds = (
                max(1.0, float(section.get("cast_seconds", 10) or 10))
                + max(0.0, float(section.get("landed_grace_seconds", 1.0) or 0.0))
            )
            for chain in self.chains.values():
                positions = chain.get("positions", {})
                expired_ids = [
                    cast_id for cast_id, item in positions.items()
                    if now - float(item.get("time") or now) > active_seconds
                ]
                for cast_id in expired_ids:
                    positions.pop(cast_id, None)
            stale = [key for key, chain in self.chains.items() if now - float(chain.get("updated") or 0) > ttl]
            for key in stale:
                self.chains.pop(key, None)
                if self.latest_key == key:
                    self.latest_key = None
            if not self.chains:
                return None

            main_chains = [
                chain for chain in self.chains.values()
                if any(not item.get("ramp") for item in chain.get("positions", {}).values())
            ]
            ramp_chains = [
                chain for chain in self.chains.values()
                if any(item.get("ramp") for item in chain.get("positions", {}).values())
            ]
            main_chain = max(main_chains, key=lambda chain: chain.get("updated") or 0) if main_chains else None
            ramp_chain = max(ramp_chains, key=lambda chain: chain.get("updated") or 0) if ramp_chains else None

            if main_chain is None:
                return ramp_chain
            if ramp_chain is None or ramp_chain is main_chain:
                return main_chain

            # CH and RCH commonly name different targets, which puts them in
            # separate chain buckets.  Render the newest active lane of each
            # together instead of allowing the newest hit to hide the other.
            positions = {
                cast_id: item
                for cast_id, item in main_chain.get("positions", {}).items()
                if not item.get("ramp")
            }
            positions.update({
                cast_id: item
                for cast_id, item in ramp_chain.get("positions", {}).items()
                if item.get("ramp")
            })
            return {
                "tag": main_chain.get("tag") or ramp_chain.get("tag") or "",
                "target": main_chain.get("target") or "Unknown",
                "ramp_target": ramp_chain.get("target") or "Unknown",
                "positions": positions,
                "metronome_started": main_chain.get("metronome_started") or now,
                "updated": max(float(main_chain.get("updated") or 0), float(ramp_chain.get("updated") or 0)),
                "latest": main_chain.get("latest") or "",
                "latest_id": main_chain.get("latest_id") or "",
                "ramp_latest": ramp_chain.get("latest") or "",
                "ramp_latest_id": ramp_chain.get("latest_id") or "",
            }

        def rounded_rect(self, cr, x, y, width, height, radius):
            radius = min(radius, width / 2, height / 2)
            cr.new_sub_path()
            cr.arc(x + width - radius, y + radius, radius, -math.pi / 2, 0)
            cr.arc(x + width - radius, y + height - radius, radius, 0, math.pi / 2)
            cr.arc(x + radius, y + height - radius, radius, math.pi / 2, math.pi)
            cr.arc(x + radius, y + radius, radius, math.pi, 3 * math.pi / 2)
            cr.close_path()

        def text_size(self, cr, text, size=24, weight=cairo.FONT_WEIGHT_NORMAL):
            cr.save()
            cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, weight)
            cr.set_font_size(size)
            extents = cr.text_extents(text)
            cr.restore()
            return extents.width, extents.height, extents.x_bearing, extents.y_bearing

        def draw_centered_text(self, cr, text, x, y, width, height, size=24, color=(1, 1, 1, 1), weight=cairo.FONT_WEIGHT_NORMAL):
            cr.save()
            cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, weight)
            cr.set_font_size(size)
            extents = cr.text_extents(text)
            cr.set_source_rgba(*color)
            cr.move_to(
                x + (width - extents.width) / 2 - extents.x_bearing,
                y + (height - extents.height) / 2 - extents.y_bearing,
            )
            cr.show_text(text)
            cr.restore()

        def draw_metronome(self, cr, chain, x, y, width, height, cast_seconds, now):
            updated = float(chain.get("updated") or now)
            elapsed = max(0.0, now - updated)
            beat_elapsed = elapsed % cast_seconds
            remaining = max(0.0, cast_seconds - beat_elapsed)
            fraction = beat_elapsed / cast_seconds
            if remaining < 0.05:
                remaining = cast_seconds
            metronome_started = float(chain.get("metronome_started") or updated)
            swing_elapsed = max(0.0, now - metronome_started)
            swing_fraction = (swing_elapsed % 2.0) / 2.0
            swing = math.sin(swing_fraction * math.pi * 2 - math.pi / 2)
            angle = swing * math.radians(30)
            display_remaining = max(0.0, remaining)
            display_quarters = int(display_remaining * 4 + 0.5)
            display_whole = display_quarters // 4
            display_decimal = (0, 3, 5, 7)[display_quarters % 4]

            self.rounded_rect(cr, x, y, width, height, 5)
            cr.set_source_rgba(0.02, 0.025, 0.03, 0.9)
            cr.fill_preserve()
            cr.set_source_rgba(0.95, 0.95, 0.98, 0.9)
            cr.set_line_width(2)
            cr.stroke()

            pivot_x = x + width / 2
            pivot_y = y + 12
            rod_length = max(22, height - 32)
            bob_x = pivot_x + math.sin(angle) * rod_length
            bob_y = pivot_y + math.cos(angle) * rod_length

            cr.set_source_rgba(1, 1, 1, 0.18)
            cr.set_line_width(1.5)
            cr.arc(pivot_x, pivot_y, rod_length, math.radians(60), math.radians(120))
            cr.stroke()

            for marker_angle in (math.radians(-30), 0, math.radians(30)):
                mark_x = pivot_x + math.sin(marker_angle) * rod_length
                mark_y = pivot_y + math.cos(marker_angle) * rod_length
                cr.set_source_rgba(1, 1, 1, 0.42 if marker_angle == 0 else 0.28)
                cr.arc(mark_x, mark_y, 2.0, 0, math.pi * 2)
                cr.fill()

            cr.set_source_rgba(0.96, 0.84, 0.26, 0.96)
            cr.set_line_width(4)
            cr.move_to(pivot_x, pivot_y)
            cr.line_to(bob_x, bob_y)
            cr.stroke()

            cr.set_source_rgba(0.98, 0.88, 0.35, 1)
            cr.arc(bob_x, bob_y, 5.5, 0, math.pi * 2)
            cr.fill_preserve()
            cr.set_source_rgba(0.08, 0.08, 0.1, 0.9)
            cr.set_line_width(1.5)
            cr.stroke()

            cr.set_source_rgba(0.95, 0.96, 0.98, 0.95)
            cr.arc(pivot_x, pivot_y, 3.5, 0, math.pi * 2)
            cr.fill()

            bar_x = x + 10
            bar_y = y + height - 15
            bar_width = max(8, width - 20)
            cr.set_source_rgba(1, 1, 1, 0.22)
            cr.set_line_width(4)
            cr.move_to(bar_x, bar_y)
            cr.line_to(bar_x + bar_width, bar_y)
            cr.stroke()
            cr.set_source_rgba(0.96, 0.84, 0.26, 0.95)
            cr.move_to(bar_x, bar_y)
            cr.line_to(bar_x + bar_width * fraction, bar_y)
            cr.stroke()
            self.draw_centered_text(cr, f"{display_whole:02d}.{display_decimal}", x, y + height - 17, width, 15, 12, (0.96, 0.84, 0.26, 1), cairo.FONT_WEIGHT_BOLD)

        def on_chain_draw(self, widget, cr):
            width = widget.get_allocated_width()
            height = widget.get_allocated_height()
            chain = self.active_chain()
            if not chain:
                return False

            now = time.time()
            section = self.section()
            cast_seconds = max(1.0, float(section.get("cast_seconds", 10) or 10))
            landed_grace = max(0.0, float(section.get("landed_grace_seconds", 1.0) or 0.0))
            positions_by_id = chain.get("positions", {})
            expired = [
                cast_id for cast_id, item in positions_by_id.items()
                if now - float(item.get("time") or now) > cast_seconds + landed_grace
            ]
            for cast_id in expired:
                positions_by_id.pop(cast_id, None)
                if chain.get("latest_id") == cast_id:
                    chain["latest_id"] = ""
                    chain["latest"] = ""

            positions = sorted(chain.get("positions", {}).values(), key=lambda item: (item.get("sort") or 0, item.get("display") or ""))
            main_positions = [item for item in positions if not item.get("ramp")]
            ramp_positions = [item for item in positions if item.get("ramp")]
            max_slots = max(1, int(self.section().get("max_slots", 8) or 8))
            main_positions = main_positions[-max_slots:]
            ramp_positions = ramp_positions[-max_slots:]

            target = str(chain.get("target") or "Unknown")
            ramp_target = str(chain.get("ramp_target") or target)
            main_label = f"CH · {target}" if main_positions else f"RCH · {target}"
            latest_end = float(chain.get("updated") or now) + cast_seconds
            hold_seconds = max(0.0, float(section.get("post_chain_visible_seconds", 30) or 0))
            if not main_positions and not ramp_positions and now > latest_end + hold_seconds:
                return False

            cr.set_line_cap(cairo.LINE_CAP_ROUND)
            cr.set_line_join(cairo.LINE_JOIN_ROUND)

            label_width = min(220, max(88, int(self.text_size(cr, main_label, 22, cairo.FONT_WEIGHT_BOLD)[0] + 18)))
            box_height = 42
            metronome_height = 68
            has_ramp_row = bool(ramp_positions)
            y_mid = max(28, min(height - 34, int(height * 0.38))) if has_ramp_row else max(34, height // 2)
            label_x = 8
            label_y = y_mid - box_height / 2
            start_x = label_x + label_width + 16
            show_metronome = bool(self.section().get("metronome", True))
            metronome_width = 92 if show_metronome else 0
            metronome_gap = 14 if show_metronome else 0
            metronome_x = width - metronome_width - 10
            end_x = max(start_x + 80, width - 14 - metronome_width - metronome_gap)
            lane_width = max(1.0, end_x - start_x)
            slot_count = max(1, int(math.ceil(cast_seconds)))
            slot_width = lane_width / slot_count
            box_width = max(8, min(72, slot_width - 6))
            box_text_size = max(8, min(26, box_width * 0.36))

            block_top = y_mid - box_height / 2 - 4
            block_height = box_height + 8
            self.rounded_rect(cr, start_x, block_top, lane_width, block_height, 5)
            cr.set_source_rgba(0.02, 0.025, 0.03, 0.16)
            cr.fill_preserve()
            cr.set_source_rgba(0.9, 0.9, 0.92, 0.28)
            cr.set_line_width(1.2)
            cr.stroke()

            for index in range(slot_count + 1):
                x = start_x + index * slot_width
                cr.set_source_rgba(1, 1, 1, 0.36 if index in (0, slot_count) else 0.18)
                cr.set_line_width(1.0)
                cr.move_to(x, block_top)
                cr.line_to(x, block_top + block_height)
                cr.stroke()
            for index in range(slot_count):
                remaining_label = index + 1
                if remaining_label <= cast_seconds:
                    self.draw_centered_text(
                        cr,
                        f"{remaining_label}s",
                        start_x + index * slot_width,
                        block_top - 16,
                        slot_width,
                        14,
                        11,
                        (1, 1, 1, 0.58),
                        cairo.FONT_WEIGHT_BOLD,
                    )

            self.rounded_rect(cr, label_x, label_y, label_width, box_height, 4)
            cr.set_source_rgba(1, 1, 1, 0.72)
            cr.fill_preserve()
            cr.set_source_rgba(0.08, 0.08, 0.1, 0.82)
            cr.set_line_width(2)
            cr.stroke()
            self.draw_centered_text(cr, main_label, label_x, label_y, label_width, box_height, 21, (0.08, 0.08, 0.1, 1), cairo.FONT_WEIGHT_BOLD)

            latest = str(chain.get("latest") or "")
            latest_id = str(chain.get("latest_id") or "")
            ramp_latest = str(chain.get("ramp_latest") or latest)
            ramp_latest_id = str(chain.get("ramp_latest_id") or latest_id)
            for item in main_positions:
                elapsed = max(0.0, now - float(item.get("time") or now))
                progress = min(1.0, elapsed / cast_seconds)
                x = end_x - box_width - (lane_width - box_width) * progress
                y = y_mid - box_height / 2
                is_latest = str(item.get("id") or "") == latest_id or (not latest_id and item.get("display") == latest)
                if is_latest:
                    fill = (0.03, 0.23, 0.0, 0.76)
                    border = (0.75, 0.95, 0.75, 0.86)
                else:
                    fill = (0.02, 0.04, 0.07, 0.62)
                    border = (0.78, 0.8, 0.86, 0.72)
                self.rounded_rect(cr, x, y, box_width, box_height, 5)
                cr.set_source_rgba(*fill)
                cr.fill_preserve()
                cr.set_source_rgba(*border)
                cr.set_line_width(2)
                cr.stroke()
                self.draw_centered_text(cr, item.get("display") or "", x, y, box_width, box_height, box_text_size, (0.96, 0.97, 1.0, 1), cairo.FONT_WEIGHT_BOLD)
            if ramp_positions:
                ramp_label = f"RCH · {ramp_target}"
                ramp_label_width = min(
                    label_width,
                    max(64, int(self.text_size(cr, ramp_label, 12, cairo.FONT_WEIGHT_BOLD)[0] + 12)),
                )
                ramp_box_width = 44
                ramp_box_height = 20
                ramp_gap = 6
                ramp_y = min(height - ramp_box_height - 6, y_mid + box_height / 2 + 8)
                ramp_x = start_x
                ramp_end_x = min(end_x, width - 12 - metronome_width - metronome_gap)
                cr.set_source_rgba(0.55, 0.78, 1.0, 0.42)
                cr.set_line_width(2)
                cr.move_to(ramp_x - 4, ramp_y + ramp_box_height / 2)
                cr.line_to(ramp_end_x, ramp_y + ramp_box_height / 2)
                cr.stroke()
                self.draw_centered_text(cr, ramp_label, ramp_x - ramp_label_width - 6, ramp_y, ramp_label_width, ramp_box_height, 12, (0.74, 0.86, 1.0, 0.95), cairo.FONT_WEIGHT_BOLD)
                for item in ramp_positions:
                    display = str(item.get("ramp_display") or item.get("display") or "")
                    pill_width = max(ramp_box_width, min(58, int(self.text_size(cr, display, 13, cairo.FONT_WEIGHT_BOLD)[0] + 18)))
                    if ramp_x + pill_width > ramp_end_x:
                        break
                    is_latest = str(item.get("id") or "") == ramp_latest_id or (not ramp_latest_id and display == ramp_latest)
                    fill = (0.02, 0.12, 0.24, 0.88) if is_latest else (0.01, 0.04, 0.08, 0.74)
                    border = (0.58, 0.82, 1.0, 0.95) if is_latest else (0.46, 0.62, 0.78, 0.82)
                    self.rounded_rect(cr, ramp_x, ramp_y, pill_width, ramp_box_height, 4)
                    cr.set_source_rgba(*fill)
                    cr.fill_preserve()
                    cr.set_source_rgba(*border)
                    cr.set_line_width(1.5)
                    cr.stroke()
                    self.draw_centered_text(cr, display, ramp_x, ramp_y, pill_width, ramp_box_height, 13, (0.92, 0.97, 1.0, 1), cairo.FONT_WEIGHT_BOLD)
                    ramp_x += pill_width + ramp_gap
            if show_metronome and metronome_x > end_x + 4:
                self.draw_metronome(cr, chain, metronome_x, y_mid - metronome_height / 2, metronome_width, metronome_height, cast_seconds, now)
            return False

        def tick(self):
            if not bool(self.section().get("toggled", False)):
                return True
            while True:
                try:
                    self.add_chain_hit(CH_CHAIN_EVENTS.get_nowait())
                except queue.Empty:
                    break
            if self.config_version != CONFIG_VERSION:
                self.apply_config()
            self.area.queue_draw()
            return True

    class FrogDanceOverlay(BaseOverlay):
        section_name = "frog_dancer"
        title = "EQ Watcher Dance Character"

        def __init__(self):
            self.frames = []
            self.scaled_frames = []
            self.loaded_character = ""
            self.frame_index = 1
            self.dance_order = (0, 1, 2, 3)
            self.dance_step = 0
            self.beat_scale = 1.0
            self.dance_started_at = 0.0
            self.beat_seconds = 0.16
            self.beat_count = 0
            self.beat_offsets = []
            self.phrase_duration = 0.0
            self.playback_mode = "midi"
            self.phrase_start_step = 0
            self.cycle_index = 0
            self.cycle_mode_active = False
            self.cycle_has_received_beat = False
            super().__init__()
            GLib.timeout_add(40, self.tick)

        def build_content(self):
            box = super().build_content()
            box.set_spacing(0)
            self.image = Gtk.Image()
            self.image.set_halign(Gtk.Align.CENTER)
            self.image.set_valign(Gtk.Align.END)
            box.pack_start(self.image, True, True, 0)
            self.clock_label = Gtk.Label(label=dancer_clock_text())
            self.clock_label.set_halign(Gtk.Align.CENTER)
            self.clock_label.set_justify(Gtk.Justification.CENTER)
            self.clock_label.get_style_context().add_class("gina-eq-clock")
            box.pack_start(self.clock_label, False, False, 0)
            self.load_character_frames()
            return box

        def load_character_frames(self):
            configured_character = str(self.section().get("character") or "yellow_cap_frog")
            if configured_character == "all":
                playlist = tuple(
                    (character, style)
                    for character, definition in DANCE_CHARACTERS.items()
                    for style in definition.get("styles", {})
                    if style != "combo"
                )
                if not playlist:
                    return
                if not self.cycle_mode_active:
                    self.cycle_index = 0
                    self.cycle_has_received_beat = False
                self.cycle_mode_active = True
                character_key, style_key = playlist[self.cycle_index % len(playlist)]
            else:
                self.cycle_mode_active = False
                self.cycle_has_received_beat = False
                character_key = configured_character
                style_key = str(self.section().get("dance_style") or "new")
            if character_key not in DANCE_CHARACTERS:
                character_key = "yellow_cap_frog"
            definition = DANCE_CHARACTERS[character_key]
            styles = definition.get("styles", {})
            if style_key not in styles:
                style_key = "new" if "new" in styles else next(iter(styles), "")
            loaded_selection = f"{character_key}:{style_key}"
            if loaded_selection == self.loaded_character and self.frames:
                return
            style = styles.get(style_key, {})
            try:
                sources = style.get("sources") or ((definition["path"], definition.get("frames", 4)),)
                frames = []
                for source in sources:
                    sprite_path, source_frame_count = source[:2]
                    frame_rects = source[2] if len(source) > 2 else ()
                    source_chroma_key = source[3] if len(source) > 3 else style.get("chroma_key")
                    sprite = GdkPixbuf.Pixbuf.new_from_file(str(sprite_path))
                    if source_chroma_key == "magenta":
                        sprite = self.make_magenta_transparent(sprite)
                    width = sprite.get_width()
                    height = sprite.get_height()
                    source_frame_count = max(1, int(source_frame_count))
                    if frame_rects:
                        frames.extend(
                            sprite.new_subpixbuf(int(x), int(y), int(frame_width), int(frame_height))
                            for x, y, frame_width, frame_height in frame_rects
                        )
                    else:
                        edges = [round(index * width / source_frame_count) for index in range(source_frame_count + 1)]
                        frames.extend(
                            sprite.new_subpixbuf(edges[index], 0, edges[index + 1] - edges[index], height)
                            for index in range(source_frame_count)
                        )
                self.frames = frames
                frame_count = len(self.frames)
                order_source = style.get("dance_order", definition.get("dance_order", range(frame_count)))
                order = tuple(int(index) % frame_count for index in order_source)
                self.dance_order = order or tuple(range(frame_count))
                scale_value = style.get("beat_scale", definition.get("beat_scale", 1.0))
                self.beat_scale = max(0.4, min(2.0, float(scale_value)))
                self.dance_step = 0
                self.phrase_start_step = 0
                self.frame_index = self.dance_order[0]
                self.loaded_character = loaded_selection
                self.scaled_frames = []
            except Exception as exc:
                broadcast("error", {"message": f"Dance character sprite unavailable: {exc}"})

        def make_magenta_transparent(self, sprite):
            """Convert the generated sheet's magenta key to real alpha."""
            width = sprite.get_width()
            height = sprite.get_height()
            channels = sprite.get_n_channels()
            rowstride = sprite.get_rowstride()
            source = sprite.get_pixels()
            output = bytearray(width * height * 4)
            for y in range(height):
                source_row = y * rowstride
                output_row = y * width * 4
                for x in range(width):
                    source_offset = source_row + x * channels
                    output_offset = output_row + x * 4
                    red = source[source_offset]
                    green = source[source_offset + 1]
                    blue = source[source_offset + 2]
                    is_key = (
                        red > 110
                        and blue > 110
                        and min(red, blue) > green * 1.8 + 30
                    )
                    output[output_offset:output_offset + 4] = (
                        red,
                        green,
                        blue,
                        0 if is_key else 255,
                    )
            return GdkPixbuf.Pixbuf.new_from_bytes(
                GLib.Bytes.new(bytes(output)),
                GdkPixbuf.Colorspace.RGB,
                True,
                8,
                width,
                height,
                width * 4,
            )

        def scale_frames(self):
            if not self.frames:
                return
            geometry = list(self.section().get("geometry") or [0, 0, 180, 180])
            while len(geometry) < 4:
                geometry.append(180)
            available_width = max(16, int(geometry[2]) - 16)
            # Leave room for the in-game clock beneath the dancer.
            available_height = max(16, int(geometry[3]) - 64)
            self.scaled_frames = []
            for frame in self.frames:
                scale = min(
                    available_width / frame.get_width(),
                    available_height / frame.get_height(),
                )
                width = max(1, int(frame.get_width() * scale))
                height = max(1, int(frame.get_height() * scale))
                self.scaled_frames.append(
                    frame.scale_simple(width, height, GdkPixbuf.InterpType.NEAREST)
                )
            self.show_frame(self.frame_index)

        def show_frame(self, index):
            if not self.scaled_frames:
                return
            self.frame_index = int(index) % len(self.scaled_frames)
            self.image.set_from_pixbuf(self.scaled_frames[self.frame_index])

        def show_dance_step(self, step):
            if not self.dance_order:
                return
            self.dance_step = int(step)
            self.show_frame(self.dance_order[self.dance_step % len(self.dance_order)])

        def apply_config(self):
            super().apply_config()
            section = self.section()
            css = """
                .gina-overlay-frog-dancer {
                    background-color: rgba(0, 0, 0, 0);
                    background-image: none;
                }
                .gina-eq-clock {
                    color: #f6e7a8;
                    background-color: rgba(22, 16, 8, 0.88);
                    border: 2px solid #d6a83f;
                    border-radius: 5px;
                    font-family: monospace;
                    font-size: 13px;
                    font-weight: 900;
                    padding: 2px 10px;
                    text-shadow: 2px 2px 2px rgba(0, 0, 0, 0.95);
                }
            """
            self.css.load_from_data(css.encode("utf-8"))
            transparent = Gdk.RGBA()
            transparent.red = transparent.green = transparent.blue = transparent.alpha = 0
            self.window.override_background_color(Gtk.StateFlags.NORMAL, transparent)
            self.load_character_frames()
            self.scale_frames()
            self.set_click_through(bool(section.get("clickthrough", True)))

        def receive_beat(self, event):
            if str(self.section().get("character") or "") == "all":
                if self.cycle_has_received_beat:
                    playlist_size = sum(
                        1
                        for definition in DANCE_CHARACTERS.values()
                        for style in definition.get("styles", {})
                        if style != "combo"
                    )
                    if playlist_size:
                        self.cycle_index = (self.cycle_index + 1) % playlist_size
                        self.loaded_character = ""
                        self.load_character_frames()
                        self.scale_frames()
                else:
                    self.cycle_has_received_beat = True
            self.playback_mode = str(event.get("playback_mode") or "midi")
            self.dance_started_at = float(event.get("started_at") or time.time())
            self.beat_seconds = max(0.04, float(event.get("beat_seconds") or 0.16))
            self.beat_count = max(1, int(event.get("beat_count") or 1))
            self.beat_offsets = [float(value) for value in event.get("beat_offsets", [])]
            self.phrase_duration = max(0.0, float(event.get("phrase_duration") or 0.0))
            if self.playback_mode == "midi":
                self.show_dance_step(self.dance_step + 1)
            else:
                self.phrase_start_step = self.dance_step
                self.show_dance_step(self.phrase_start_step)

        def tick(self):
            while True:
                try:
                    self.receive_beat(FROG_BEAT_EVENTS.get_nowait())
                except queue.Empty:
                    break
            if self.config_version != CONFIG_VERSION:
                self.apply_config()
            clock_text = dancer_clock_text()
            if self.clock_label.get_text() != clock_text:
                self.clock_label.set_text(clock_text)
            if self.playback_mode != "midi" and self.dance_started_at:
                elapsed = time.time() - self.dance_started_at
                if self.beat_offsets and 0 <= elapsed < self.phrase_duration:
                    completed = sum(1 for offset in self.beat_offsets if offset <= elapsed)
                    self.show_dance_step(self.phrase_start_step + max(0, completed - 1))
                elif self.beat_offsets and elapsed >= self.phrase_duration:
                    self.dance_started_at = 0.0
                    self.show_dance_step(self.phrase_start_step + len(self.beat_offsets))
                elif 0 <= elapsed < self.beat_seconds * self.beat_count:
                    step_seconds = self.beat_seconds * self.beat_scale
                    self.show_dance_step(self.phrase_start_step + int(elapsed / step_seconds))
                elif elapsed >= self.beat_seconds * self.beat_count:
                    self.dance_started_at = 0.0
                    step_seconds = self.beat_seconds * self.beat_scale
                    completed_steps = max(1, int(math.ceil(
                        self.beat_seconds * self.beat_count / step_seconds
                    )))
                    self.show_dance_step(self.phrase_start_step + completed_steps)
            return bool(STATE["running"])

    class Controller:
        def __init__(self):
            self.windows = {
                "text_overlay": TextOverlay(),
                "maps": MapsOverlay(),
                "nparse_spells": NParseSpellsOverlay(),
                "rolls": RollOverlay(),
                "frog_dancer": FrogDanceOverlay(),
                "dps": DPSOverlay(),
                "aggro": AggroOverlay(),
                "ch_chain": CHChainOverlay(),
                "discord": DiscordOverlay(),
            }
            self.tray_menu = None
            self.tray_icon = None
            self.create_tray_icon()
            self.apply_all()
            GLib.timeout_add(250, self.tick)

        def create_tray_icon(self):
            try:
                self.tray_icon = Gtk.StatusIcon.new_from_icon_name("utilities-system-monitor")
                self.tray_icon.set_visible(True)
                self.tray_icon.set_tooltip_text("EQ Watcher")
                self.tray_icon.connect("activate", self.on_tray_activate)
                self.tray_icon.connect("popup-menu", self.on_tray_popup_menu)
            except Exception as exc:
                broadcast("error", {"message": f"Tray icon unavailable: {exc}"})

        def section(self, section_name):
            with CONFIG_LOCK:
                section = dict(DEFAULT_CONFIG["nparse"].get(section_name, {}))
                section.update(CONFIG.get("nparse", {}).get(section_name, {}))
            return section

        def update_section(self, section_name, **changes):
            with CONFIG_LOCK:
                nparse = dict(CONFIG.get("nparse", DEFAULT_CONFIG["nparse"]))
                section = dict(DEFAULT_CONFIG["nparse"].get(section_name, {}))
                section.update(nparse.get(section_name, {}))
                section.update(changes)
                nparse[section_name] = section
                CONFIG["nparse"] = nparse
                save_config(CONFIG)
            self.apply_all()

        def build_tray_menu(self):
            menu = Gtk.Menu()

            open_item = Gtk.MenuItem(label="Open EQ Watcher")
            open_item.connect("activate", self.on_open_ui)
            menu.append(open_item)

            menu.append(self.section_check_item("Maps Overlay", "maps", "toggled"))
            menu.append(self.section_check_item("Maps Click-through", "maps", "clickthrough"))
            menu.append(self.maps_edit_frame_item())
            menu.append(self.section_check_item("Maps Auto follow", "maps", "auto_follow"))
            menu.append(self.section_check_item(
                "Maps Hide after 30s without /loc",
                "maps",
                "hide_when_location_stale",
            ))
            menu.append(self.section_check_item("Maps Grid", "maps", "show_grid"))
            menu.append(self.section_check_item("Maps POI", "maps", "show_poi"))
            menu.append(Gtk.SeparatorMenuItem())
            menu.append(self.section_check_item("Text Overlay", "text_overlay", "toggled"))
            menu.append(self.section_check_item("Text Overlay Click-through", "text_overlay", "clickthrough"))
            menu.append(self.text_overlay_edit_frame_item())
            menu.append(Gtk.SeparatorMenuItem())
            menu.append(self.section_check_item("Spell Timers Overlay", "nparse_spells", "toggled"))
            menu.append(self.section_check_item("Spell Timers Click-through", "nparse_spells", "clickthrough"))
            menu.append(self.nparse_spells_edit_frame_item())
            menu.append(Gtk.SeparatorMenuItem())
            menu.append(self.section_check_item("Roll Overlay", "rolls", "toggled"))
            menu.append(self.section_check_item("Roll Overlay Click-through", "rolls", "clickthrough"))
            menu.append(self.rolls_edit_frame_item())
            menu.append(Gtk.SeparatorMenuItem())
            menu.append(self.section_check_item("Dance Character Overlay", "frog_dancer", "toggled"))
            menu.append(self.frog_dancer_edit_frame_item())
            menu.append(Gtk.SeparatorMenuItem())
            menu.append(self.section_check_item("DPS Overlay", "dps", "toggled"))
            menu.append(self.section_check_item("DPS Click-through", "dps", "clickthrough"))
            menu.append(self.dps_edit_frame_item())
            menu.append(Gtk.SeparatorMenuItem())
            menu.append(self.section_check_item("Aggro Overlay", "aggro", "toggled"))
            menu.append(self.section_check_item("Aggro Click-through", "aggro", "clickthrough"))
            menu.append(self.aggro_edit_frame_item())
            menu.append(Gtk.SeparatorMenuItem())
            menu.append(self.section_check_item("CH Chain Overlay", "ch_chain", "toggled"))
            menu.append(self.section_check_item("CH Chain Click-through", "ch_chain", "clickthrough"))
            menu.append(self.ch_chain_edit_frame_item())
            menu.append(Gtk.SeparatorMenuItem())
            menu.append(self.section_check_item("Discord Overlay", "discord", "toggled"))
            menu.append(self.section_check_item("Discord Click-through", "discord", "clickthrough"))
            menu.append(Gtk.SeparatorMenuItem())

            toggle_voice = Gtk.MenuItem(label=f"Toggle Voice ({'On' if bool(CONFIG.get('speak', True)) else 'Off'})")
            toggle_voice.connect("activate", self.on_toggle_voice)
            menu.append(toggle_voice)

            toggle_beep = Gtk.MenuItem(label=f"Toggle Beep ({'On' if bool(CONFIG.get('beep', True)) else 'Off'})")
            toggle_beep.connect("activate", self.on_toggle_beep)
            menu.append(toggle_beep)

            menu.append(Gtk.SeparatorMenuItem())

            quit_item = Gtk.MenuItem(label="Quit")
            quit_item.connect("activate", self.on_quit)
            menu.append(quit_item)

            menu.show_all()
            return menu

        def section_check_item(self, label, section_name, key):
            item = Gtk.CheckMenuItem(label=label)
            item.set_active(bool(self.section(section_name).get(key, False)))
            item.connect("toggled", self.on_toggle_section_value, section_name, key)
            return item

        def nparse_spells_edit_frame_item(self):
            section = self.section("nparse_spells")
            item = Gtk.CheckMenuItem(label="Spell Timers Edit Frame")
            item.set_active(not bool(section.get("frameless", True)))
            item.connect("toggled", self.on_toggle_nparse_spells_edit_frame)
            return item

        def rolls_edit_frame_item(self):
            section = self.section("rolls")
            item = Gtk.CheckMenuItem(label="Roll Overlay Edit Frame")
            item.set_active(not bool(section.get("frameless", True)))
            item.connect("toggled", self.on_toggle_rolls_edit_frame)
            return item

        def frog_dancer_edit_frame_item(self):
            section = self.section("frog_dancer")
            item = Gtk.CheckMenuItem(label="Dance Character Edit Frame")
            item.set_active(not bool(section.get("frameless", True)))
            item.connect("toggled", self.on_toggle_frog_dancer_edit_frame)
            return item

        def maps_edit_frame_item(self):
            section = self.section("maps")
            item = Gtk.CheckMenuItem(label="Maps Edit Frame")
            item.set_active(not bool(section.get("frameless", True)))
            item.connect("toggled", self.on_toggle_maps_edit_frame)
            return item

        def ch_chain_edit_frame_item(self):
            section = self.section("ch_chain")
            item = Gtk.CheckMenuItem(label="CH Chain Edit Frame")
            item.set_active(not bool(section.get("frameless", True)))
            item.connect("toggled", self.on_toggle_ch_chain_edit_frame)
            return item

        def dps_edit_frame_item(self):
            section = self.section("dps")
            item = Gtk.CheckMenuItem(label="DPS Edit Frame")
            item.set_active(not bool(section.get("frameless", True)))
            item.connect("toggled", self.on_toggle_dps_edit_frame)
            return item

        def aggro_edit_frame_item(self):
            section = self.section("aggro")
            item = Gtk.CheckMenuItem(label="Aggro Edit Frame")
            item.set_active(not bool(section.get("frameless", True)))
            item.connect("toggled", self.on_toggle_aggro_edit_frame)
            return item

        def text_overlay_edit_frame_item(self):
            section = self.section("text_overlay")
            item = Gtk.CheckMenuItem(label="Text Overlay Edit Frame")
            item.set_active(not bool(section.get("frameless", True)))
            item.connect("toggled", self.on_toggle_text_overlay_edit_frame)
            return item

        def on_toggle_section_value(self, item, section_name, key, *_args):
            self.update_section(section_name, **{key: item.get_active()})

        def on_toggle_maps_edit_frame(self, item, *_args):
            edit_frame = item.get_active()
            self.update_section(
                "maps",
                frameless=not edit_frame,
                clickthrough=not edit_frame,
            )

        def on_toggle_nparse_spells_edit_frame(self, item, *_args):
            edit_frame = item.get_active()
            self.update_section(
                "nparse_spells",
                frameless=not edit_frame,
                clickthrough=not edit_frame,
            )

        def on_toggle_rolls_edit_frame(self, item, *_args):
            edit_frame = item.get_active()
            changes = {
                "frameless": not edit_frame,
                "clickthrough": not edit_frame,
            }
            if not edit_frame:
                # A configure-event saves geometry on a short debounce.  The
                # tray toggle can otherwise make the window frameless and
                # reapply its previous geometry before that callback runs.
                # Capture the decorated window's content origin while it is
                # still available and persist it in the same config update.
                overlay = self.windows.get("rolls")
                if overlay is not None:
                    if overlay.pending_geometry_save is not None:
                        try:
                            GLib.source_remove(overlay.pending_geometry_save)
                        except Exception:
                            pass
                        overlay.pending_geometry_save = None
                    changes["geometry"] = overlay.current_content_geometry()
            self.update_section(
                "rolls",
                **changes,
            )

        def on_toggle_ch_chain_edit_frame(self, item, *_args):
            edit_frame = item.get_active()
            self.update_section(
                "ch_chain",
                frameless=not edit_frame,
                clickthrough=not edit_frame,
            )

        def on_toggle_frog_dancer_edit_frame(self, item, *_args):
            edit_frame = item.get_active()
            self.update_section(
                "frog_dancer",
                frameless=not edit_frame,
                clickthrough=not edit_frame,
            )

        def on_toggle_dps_edit_frame(self, item, *_args):
            edit_frame = item.get_active()
            self.update_section(
                "dps",
                frameless=not edit_frame,
                clickthrough=not edit_frame,
            )

        def on_toggle_aggro_edit_frame(self, item, *_args):
            edit_frame = item.get_active()
            self.update_section(
                "aggro",
                frameless=not edit_frame,
                clickthrough=not edit_frame,
            )

        def on_toggle_text_overlay_edit_frame(self, item, *_args):
            edit_frame = item.get_active()
            self.update_section(
                "text_overlay",
                frameless=not edit_frame,
                clickthrough=not edit_frame,
            )

        def on_tray_activate(self, _icon):
            self.open_ui()

        def on_tray_popup_menu(self, icon, button, activate_time):
            self.tray_menu = self.build_tray_menu()
            self.tray_menu.popup(
                None,
                None,
                Gtk.StatusIcon.position_menu,
                icon,
                button,
                activate_time,
            )

        def open_ui(self):
            url = STATE.get("ui_url", "")
            if url:
                webbrowser.open_new_tab(f"{url}?reuse=1")

        def on_open_ui(self, *_args):
            self.open_ui()

        def on_toggle_voice(self, *_args):
            self.toggle_config_flag("speak", "Voice")

        def on_toggle_beep(self, *_args):
            self.toggle_config_flag("beep", "Beep")

        def on_quit(self, *_args):
            request_shutdown()
            Gtk.main_quit()

        def apply_all(self):
            for window in self.windows.values():
                window.apply_config()

        def tick(self):
            for window in self.windows.values():
                window.tick()
            return True

        def toggle_config_flag(self, key, label):
            with CONFIG_LOCK:
                CONFIG[key] = not bool(CONFIG.get(key, True))
                save_config(CONFIG)
                value = bool(CONFIG[key])
            broadcast("status", {
                "message": f"{label} {'enabled' if value else 'disabled'}",
                "active_log": STATE.get("active_log", ""),
                "character": STATE.get("character", ""),
                "speak": CONFIG.get("speak", True),
                "beep": CONFIG.get("beep", True),
            })

        def clear_overlay_timer(self, timer_id, trigger_id=""):
            timer_id = str(timer_id or "").strip()
            trigger_id = str(trigger_id or "").strip()
            if not timer_id and not trigger_id:
                return False
            overlay = self.windows.get("nparse_spells")
            if overlay is None:
                return False

            def clear_on_overlay_thread():
                overlay.clear_timer(timer_id, trigger_id)
                return False

            GLib.idle_add(clear_on_overlay_thread)
            return True

        def clear_overlay_timers(self):
            overlay = self.windows.get("nparse_spells")
            if overlay is not None:
                GLib.idle_add(lambda: (overlay.clear_all_timers(), False)[1])

        def clear_rolls(self):
            overlay = self.windows.get("rolls")
            if overlay is not None:
                GLib.idle_add(lambda: (overlay.clear_all_rolls(), False)[1])

    global OVERLAY_CONTROLLER
    OVERLAY_CONTROLLER = Controller()
    Gtk.main()


HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>EQ Watcher</title>
  <style>
    :root {
      color-scheme: dark;
      --bg:#0b0d0f;
      --panel:#14181c;
      --panel-2:#101316;
      --line:#2a3138;
      --line-strong:#3b4651;
      --text:#eef4fa;
      --muted:#9aa7b2;
      --accent:#5aa7ff;
      --amber:#f5d44f;
      --green:#32d583;
      --orange:#ff8a3d;
      --danger:#ff5d6c;
    }
    * { box-sizing: border-box; }
    body { margin:0; font:14px/1.35 "Aptos", "Segoe UI", sans-serif; background:linear-gradient(180deg,#0e1114 0,#08090a 100%); color:var(--text); }
    header { height:58px; display:flex; align-items:center; gap:18px; padding:0 18px; border-bottom:1px solid var(--line); background:#080a0c; }
    h1 { font-size:18px; margin:0; font-weight:750; letter-spacing:0; }
    main { height:calc(100vh - 58px); min-height:620px; display:flex; flex-direction:column; }
    section { padding:14px; }
    label { display:block; color:var(--muted); font-size:12px; margin:12px 0 5px; }
    input, select, textarea, button { font:inherit; }
    input, select, textarea { width:100%; color:var(--text); background:#090b0d; border:1px solid var(--line); border-radius:4px; padding:8px; }
    textarea { min-height:62px; resize:vertical; }
    button { border:1px solid var(--line-strong); background:#20262c; color:var(--text); border-radius:4px; padding:8px 10px; cursor:pointer; }
    button.primary { background:#1d5d96; border-color:#337fbd; }
    button.danger { background:#4a161d; border-color:#8b2c39; color:#ffd3d8; }
    .row { display:flex; gap:8px; align-items:center; }
    .row > * { flex:1; }
    .checks { display:grid; grid-template-columns:1fr 1fr; gap:8px; margin-top:12px; }
    .check { display:flex; gap:8px; align-items:center; color:var(--muted); }
    .check input { width:auto; }
    .compact-check { flex:0 0 auto; margin:0; white-space:nowrap; }
    .inline-field { flex:0 0 auto; display:flex; align-items:center; gap:6px; margin:0; white-space:nowrap; }
    .inline-field input { width:58px; padding:5px 6px; }
    .status { color:var(--muted); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; max-width:520px; }
    .pill { display:inline-flex; align-items:center; gap:6px; border:1px solid var(--line); border-radius:999px; padding:4px 9px; color:var(--muted); background:#11161a; }
    .dot { width:8px; height:8px; border-radius:50%; background:#22c55e; }
    .brand p.subtitle { margin:3px 0 0; font-size:12px; color:var(--muted); }
    .status-group { display:flex; gap:10px; align-items:center; margin-left:auto; }
    .metric { display:grid; gap:2px; min-width:74px; padding:6px 10px; border-left:1px solid var(--line); }
    .metric strong { font-size:16px; line-height:1; }
    .metric span { color:var(--muted); font-size:11px; }
    .panel { background:rgba(255,255,255,0.025); border:1px solid var(--line); border-radius:6px; padding:12px; margin-bottom:12px; }
    details.panel { padding:0; overflow:hidden; }
    details.panel > summary { list-style:none; cursor:pointer; display:flex; align-items:center; justify-content:space-between; gap:12px; padding:12px; color:var(--text); font-weight:700; }
    details.panel > summary::-webkit-details-marker { display:none; }
    details.panel > summary::after { content:""; width:8px; height:8px; border-right:2px solid var(--muted); border-bottom:2px solid var(--muted); transform:rotate(45deg); margin-right:3px; transition:transform .14s ease; }
    details.panel[open] > summary { border-bottom:1px solid var(--line); }
    details.panel[open] > summary::after { transform:rotate(225deg); }
    .panel-body { padding:12px; }
    .panel-title { display:flex; justify-content:space-between; align-items:center; gap:12px; margin-bottom:10px; }
    .panel-title span { font-weight:600; }
    button.secondary { background:#1f2730; border-color:#2f3a46; color:#cbd5e1; }
    button.full-width { width:100%; }
    .section-header { display:flex; align-items:center; justify-content:space-between; gap:12px; margin-bottom:12px; }
    .section-header h2 { margin:0; font-size:17px; }
    .actions { display:flex; gap:8px; flex-wrap:wrap; }
    .muted { color:var(--muted); }
    .grid.two { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:10px; }
    .tabs { display:flex; gap:6px; padding:10px 14px 0; border-bottom:1px solid var(--line); background:#0b0e11; overflow:auto; }
    .tab-button { flex:0 0 auto; border:1px solid transparent; border-bottom:0; background:transparent; color:var(--muted); padding:9px 13px; border-radius:6px 6px 0 0; }
    .tab-button:hover { color:var(--text); background:#14191e; }
    .tab-button.active { color:var(--text); background:#11161a; border-color:var(--line); box-shadow:inset 0 2px 0 var(--accent); }
    .tab-content { flex:1; min-height:0; overflow:hidden; }
    .tab-panel { display:none; height:100%; overflow:auto; background:#0d1115; }
    .tab-panel.active { display:block; }
    .live-grid { display:grid; grid-template-columns:minmax(460px,1.35fr) minmax(380px,0.9fr); gap:14px; align-items:start; }
    .settings-grid { display:grid; grid-template-columns:repeat(2,minmax(320px,1fr)); gap:14px; align-items:start; }
    .settings-grid .wide, .live-grid .wide { grid-column:1 / -1; }
    .panel-stack { display:grid; gap:12px; }
    .panel-stack .panel, .settings-grid .panel, .live-grid .panel { margin-bottom:0; }
    .log-panel { margin-top:12px; padding:12px; background:#101419; border:1px solid var(--line); border-radius:6px; }
    .label-row { display:flex; justify-content:space-between; gap:12px; align-items:center; margin-bottom:10px; color:var(--muted); font-size:13px; }
    .log-table-wrap { margin-top:10px; border:1px solid var(--line); border-radius:6px; overflow:auto; background:#0b0e11; }
    .log-table { width:100%; min-width:640px; border-collapse:collapse; table-layout:fixed; }
    .log-table th, .log-table td { padding:8px 10px; border-bottom:1px solid #20262d; text-align:left; vertical-align:top; }
    .log-table th { color:var(--muted); font-size:11px; text-transform:uppercase; letter-spacing:.04em; background:#090b0d; }
    .log-table tbody tr:last-child td { border-bottom:0; }
    .log-table .log-name, .log-table .log-character, .log-table .log-seen { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
    .log-table .log-zone { color:#dbeafe; font-weight:600; white-space:normal; word-break:break-word; }
    .log-table .is-stale .log-seen, .log-table .is-stale .log-zone { color:#fbbf24; }
    .log-stale-badge { display:inline-block; margin-left:6px; padding:1px 5px; border:1px solid #92400e; border-radius:999px; color:#fbbf24; font-size:10px; font-weight:700; line-height:1.4; text-transform:uppercase; vertical-align:1px; }
    .log-table .log-empty { color:var(--muted); text-align:center; padding:16px 10px; }
    .log-table .is-active { background:rgba(90, 167, 255, 0.08); }
    .favorite-cell { text-align:center; }
    .favorite-cell input { width:auto; accent-color:var(--amber); }
    .full-width { width:100%; }
    .volume-control { margin-top:10px; padding:10px 12px; border:1px solid var(--line); border-radius:6px; background:#0b0e11; }
    .volume-control .volume-head { display:flex; justify-content:space-between; gap:12px; color:var(--muted); font-size:12px; font-weight:700; text-transform:uppercase; }
    .volume-control output { color:var(--amber); font-variant-numeric:tabular-nums; }
    .volume-control input[type="range"] { width:100%; margin-top:8px; padding:0; accent-color:var(--accent); }
    .console { background:#0d1115; }
    .timer-stack { display:grid; gap:8px; margin-bottom:12px; }
    .timer-row { display:grid; grid-template-columns:8px minmax(0,1fr) auto auto; gap:12px; align-items:center; min-height:54px; padding:9px 12px; background:#050606; border:1px solid #1f2930; border-radius:4px; box-shadow:inset 0 0 0 1px rgba(255,255,255,0.03); }
    .timer-strip { align-self:stretch; border-radius:2px; background:var(--accent); }
    .timer-name { font-weight:750; font-size:17px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
    .timer-time { color:var(--amber); font-size:25px; font-weight:850; font-variant-numeric:tabular-nums; }
    .timer-clear { width:28px; min-width:28px; height:28px; padding:0; font-weight:800; line-height:1; }
    .scout-card { display:grid; grid-template-columns:8px minmax(0,1fr) auto; gap:12px; align-items:center; min-height:72px; padding:11px 12px; background:#050606; border:1px solid #1f2930; border-radius:4px; }
    .scout-card .timer-strip { background:#a78bfa; }
    .ring8-card .timer-strip { background:#f59e0b; }
    .ring8-entry { display:grid; grid-template-columns:minmax(180px,1fr) auto auto; gap:8px; align-items:end; margin-bottom:10px; }
    .ring8-entry label { margin-top:0; }
    .field-error { min-height:18px; margin-top:6px; color:#fda4af; font-size:12px; }
    .scout-meta { margin-top:3px; color:var(--muted); font-size:12px; }
    .scout-badge { display:inline-block; margin-left:6px; padding:1px 6px; border:1px solid #7c3aed; border-radius:999px; color:#c4b5fd; font-size:10px; font-weight:700; text-transform:uppercase; vertical-align:2px; }
    .scout-countdown { min-width:105px; text-align:right; }
    .scout-countdown .timer-time { display:block; }
    .scout-state { color:var(--muted); font-size:11px; text-transform:uppercase; }
    .dps-summary { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:8px; margin-bottom:10px; }
    .dps-stat { border:1px solid var(--line); border-radius:4px; background:#090b0d; padding:8px; min-width:0; }
    .dps-stat strong { display:block; font-size:17px; line-height:1.1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
    .dps-stat span { color:var(--muted); font-size:11px; text-transform:uppercase; }
    .dps-controls { display:grid; grid-template-columns:minmax(110px,0.8fr) minmax(150px,1.2fr) repeat(2,minmax(120px,0.9fr)) auto; gap:8px; align-items:end; margin-bottom:10px; }
    .dps-controls .row { align-items:end; }
    .dps-controls label { margin-top:0; }
    .dps-table { width:100%; border-collapse:collapse; table-layout:fixed; background:#0b0e11; border:1px solid var(--line); border-radius:6px; overflow:hidden; }
    .dps-table th, .dps-table td { padding:6px 8px; border-bottom:1px solid #20262d; text-align:right; font-variant-numeric:tabular-nums; }
    .dps-table th { color:var(--muted); font-size:11px; text-transform:uppercase; background:#090b0d; }
    .dps-table td:first-child, .dps-table th:first-child { text-align:left; }
    .dps-table tbody tr:last-child td { border-bottom:0; }
    .dps-name { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
    .empty { color:var(--muted); border:1px dashed var(--line-strong); border-radius:6px; padding:18px; text-align:center; background:#0d1013; }
    .alerts { display:grid; gap:7px; }
    .alert { display:grid; grid-template-columns:6px minmax(0,1fr) auto; gap:10px; align-items:start; border:1px solid var(--line); border-radius:4px; background:#14191e; padding:9px; }
    .alert h2 { margin:0; font-size:14px; line-height:1.25; }
    .alert-meta { color:var(--muted); font-size:12px; margin-top:2px; }
    .alert-time { color:var(--amber); font-size:17px; font-weight:800; font-variant-numeric:tabular-nums; }
    .alert .logline { grid-column:2 / -1; }
    .logline { margin-top:8px; color:#cbd5e1; background:#090b0d; border-radius:4px; padding:9px; max-height:95px; overflow:auto; }
    .trigger-tools { display:grid; grid-template-columns:minmax(0,1fr) auto; gap:8px; margin-bottom:10px; }
    .trigger-list { border:1px solid var(--line); border-radius:6px; overflow:hidden; background:#0f1215; }
    .trigger-head, .trigger-item { display:grid; grid-template-columns:34px minmax(130px,0.8fr) minmax(220px,1.3fr) 90px 92px; gap:8px; align-items:center; padding:8px 10px; }
    .trigger-head { color:var(--muted); font-size:11px; text-transform:uppercase; letter-spacing:.04em; background:#090b0d; border-bottom:1px solid var(--line); position:sticky; top:0; z-index:1; }
    .trigger-card { border-bottom:1px solid #20262d; }
    .trigger-card:last-child { border-bottom:0; }
    .trigger-item .row { justify-content:flex-end; }
    .trigger-item input[type="checkbox"] { width:auto; }
    .trigger-name { font-weight:700; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
    .trigger-message { color:#dbeafe; white-space:normal; overflow-wrap:anywhere; }
    .trigger-details { margin:0 10px 10px 52px; border:1px solid #293139; border-radius:5px; background:#0a0d10; overflow:hidden; }
    .trigger-details > summary { cursor:pointer; padding:6px 9px; color:#9fc8ef; font-size:12px; font-weight:700; }
    .trigger-details[open] > summary { border-bottom:1px solid #293139; }
    .trigger-detail-grid { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:8px; padding:9px; }
    .trigger-detail { min-width:0; padding:7px 8px; border:1px solid #202830; border-radius:4px; background:#10151a; }
    .trigger-detail.wide { grid-column:1 / -1; }
    .trigger-detail-label { margin-bottom:3px; color:var(--muted); font-size:10px; font-weight:800; letter-spacing:.04em; text-transform:uppercase; }
    .trigger-detail-value { color:#e7edf4; white-space:pre-wrap; overflow-wrap:anywhere; }
    .trigger-detail-value.code { color:#c6d0dc; font-family:"Cascadia Mono","Consolas",monospace; font-size:12px; }
    .nparse-card { display:grid; gap:10px; }
    .map-toolbar { display:grid; grid-template-columns:minmax(0,1fr) 120px minmax(0,1.1fr); gap:8px; align-items:end; }
    .map-toolbar .check { white-space:nowrap; }
    .map-frame { border:1px solid var(--line); border-radius:6px; background:#090b0d; padding:8px; }
    .map-frame svg { display:block; width:100%; height:270px; }
    .nparse-info { display:flex; justify-content:space-between; gap:10px; align-items:center; color:var(--muted); font-size:12px; }
    .mini-list { display:grid; gap:6px; }
    .mini-row { display:grid; grid-template-columns:minmax(0,1fr) auto auto; gap:8px; align-items:center; padding:8px; border:1px solid var(--line); border-radius:4px; background:#0b0e11; }
    .mini-name { font-weight:700; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
    .mini-meta { color:var(--muted); font-size:12px; }
    .spellbook-toolbar { display:grid; grid-template-columns:minmax(130px,.7fr) minmax(220px,1.5fr) minmax(130px,.7fr) 100px auto; gap:8px; align-items:end; }
    .spellbook-toolbar label { margin-top:0; }
    .spellbook-summary { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:8px; margin:12px 0; }
    .spellbook-stat { border:1px solid var(--line); border-radius:4px; background:#090b0d; padding:10px; min-width:0; }
    .spellbook-stat strong { display:block; font-size:20px; line-height:1.1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
    .spellbook-stat span { color:var(--muted); font-size:11px; text-transform:uppercase; }
    .spell-levels { display:grid; gap:10px; }
    .spell-level { border:1px solid var(--line); border-radius:6px; background:#0b0e11; overflow:hidden; }
    .spell-level-head { display:flex; justify-content:space-between; gap:10px; align-items:center; padding:9px 11px; border-bottom:1px solid var(--line); background:#10151a; }
    .spell-level-head strong { font-size:15px; }
    .spell-level-head a { color:#8ec5ff; font-size:12px; text-decoration:none; }
    .spell-columns { display:grid; grid-template-columns:1fr 1fr; }
    .spell-column { padding:10px 11px; min-width:0; }
    .spell-column + .spell-column { border-left:1px solid var(--line); }
    .spell-column h3 { margin:0 0 7px; color:var(--muted); font-size:11px; text-transform:uppercase; }
    .spell-list { display:flex; flex-wrap:wrap; gap:6px; }
    .spell-chip { border:1px solid #28543b; border-radius:999px; background:#0c2518; color:#a7f3d0; padding:3px 8px; font-size:12px; }
    .spell-chip.missing { border-color:#71313a; background:#291116; color:#fecdd3; }
    .spell-complete { color:#86efac; }
    .spellbook-path { margin-top:8px; color:var(--muted); font-size:12px; overflow-wrap:anywhere; }
    .inventory-toolbar { display:grid; grid-template-columns:minmax(220px,1.4fr) minmax(150px,.7fr) auto auto; gap:8px; align-items:end; }
    .inventory-toolbar .check { align-self:center; margin:20px 0 0; white-space:nowrap; }
    .inventory-summary { display:flex; flex-wrap:wrap; gap:8px; margin:12px 0; }
    .inventory-table-wrap { overflow:auto; max-height:calc(100vh - 300px); border:1px solid var(--line); border-radius:6px; }
    .inventory-table { width:100%; border-collapse:collapse; background:#0b0e11; }
    .inventory-table th { position:sticky; top:0; z-index:1; color:var(--muted); background:#090b0d; text-align:left; text-transform:uppercase; font-size:11px; letter-spacing:.04em; }
    .inventory-table th, .inventory-table td { padding:8px 10px; border-bottom:1px solid var(--line); white-space:nowrap; }
    .inventory-table tbody tr:last-child td { border-bottom:0; }
    .inventory-table tbody tr:hover { background:#111820; }
    .swatch { width:12px; height:28px; border-radius:2px; }
    .small-btn { padding:5px 7px; font-size:12px; }
    @media (max-width: 1280px) { .live-grid, .settings-grid { grid-template-columns:1fr; } }
    @media (max-width: 760px) { header { height:auto; align-items:flex-start; padding:12px; flex-wrap:wrap; } main { height:auto; min-height:0; } .tab-content { overflow:visible; } .tab-panel { height:auto; } .status-group { width:100%; margin-left:0; flex-wrap:wrap; } .dps-controls, .map-toolbar, .grid.two, .ring8-entry, .spellbook-toolbar, .spellbook-summary, .spell-columns, .inventory-toolbar { grid-template-columns:1fr; } .spell-column + .spell-column { border-left:0; border-top:1px solid var(--line); } .trigger-head { display:none; } .trigger-item { grid-template-columns:26px minmax(0,1fr) auto; align-items:start; } .trigger-item > .swatch { grid-column:1; grid-row:1; } .trigger-name { grid-column:2; grid-row:1; } .trigger-actions { grid-column:3; grid-row:1; } .trigger-message { grid-column:2 / -1; grid-row:2; } .trigger-timer-summary { grid-column:2 / -1; grid-row:3; } .trigger-details { margin-left:36px; } .trigger-detail-grid { grid-template-columns:1fr; } .trigger-detail.wide { grid-column:auto; } }
  </style>
</head>
<body>
  <header>
    <div class="brand">
      <h1>EQ Watcher</h1>
      <p class="subtitle">EverQuest log triggers, timers, overlay, and imported GINA packages.</p>
    </div>
    <div class="status-group">
      <span class="pill"><span class="dot"></span><span id="watching">Starting</span></span>
      <span class="metric"><strong id="timerCount">0</strong><span>timers</span></span>
      <span class="metric"><strong id="alertCount">0</strong><span>alerts</span></span>
      <span class="status" id="activeLog"></span>
    </div>
  </header>
  <main>
    <nav class="tabs" aria-label="EQ Watcher sections">
      <button class="tab-button active" data-tab="live">Live</button>
      <button class="tab-button" data-tab="setup">Setup</button>
      <button class="tab-button" data-tab="triggers">Triggers</button>
      <button class="tab-button" data-tab="spellbook">Spellbook</button>
      <button class="tab-button" data-tab="inventory">Inventory</button>
      <button class="tab-button" data-tab="maps">Maps</button>
    </nav>
    <div class="tab-content">
    <section class="tab-panel console active" id="tab-live">
      <div class="live-grid">
        <div class="panel-stack">
          <div class="panel">
            <div class="section-header">
              <div>
                <h2>Scout Timer</h2>
                <div class="muted">Green server · Scout Charisa</div>
              </div>
              <button class="secondary small-btn" onclick="refreshScoutTimer(true)">Refresh</button>
            </div>
            <div id="scoutTimer"><div class="empty">Loading Scout timer...</div></div>
          </div>
          <div class="panel">
            <div class="section-header">
              <div>
                <h2>Ring 8 Timer</h2>
                <div class="muted">Enter the roll time in Eastern time. It appears in Spell Timers for the final 30 minutes.</div>
              </div>
            </div>
            <div class="ring8-entry">
              <label>Roll time
                <input id="ring8Input" type="text" placeholder="10:54pm" autocomplete="off">
              </label>
              <button class="primary" onclick="setRing8Timer()">Set timer</button>
              <button class="secondary" onclick="clearRing8Timer()">Clear</button>
            </div>
            <div class="muted">Examples: 10:54pm, 22:54, tomorrow 10:54pm, 8/30 10:54pm, or 2026-08-30 22:54.</div>
            <div class="field-error" id="ring8Error"></div>
            <div id="ring8Timer"><div class="empty">No Ring 8 roll time set.</div></div>
          </div>
          <div class="panel">
            <div class="section-header">
              <div>
                <h2>Active Timers</h2>
                <div class="muted">Active countdowns from matched trigger timers.</div>
              </div>
              <div class="actions">
                <button onclick="testAlert()">Test</button>
                <button class="secondary" onclick="clearActiveTimers()">Clear timers</button>
                <button class="secondary" onclick="clearRolls()">Clear rolls</button>
                <button class="secondary" onclick="clearAlerts()">Clear alerts</button>
              </div>
            </div>
            <div class="timer-stack" id="timers"></div>
          </div>
          <div class="panel">
            <div class="section-header">
              <div>
                <h2>Recent Alerts</h2>
                <div class="muted">Newest matches first</div>
              </div>
            </div>
            <div class="alerts" id="alerts"></div>
          </div>
        </div>
        <div class="panel-stack">
          <details class="panel" open>
            <summary>Log Source</summary>
            <div class="panel-body">
              <label>Log folder</label>
              <input id="logDir">
              <label>Active log</label>
              <select id="activeLogSelect"></select>
              <div class="status" id="activeLogSummary" style="margin-top:8px"></div>
              <div class="checks">
                <label class="check"><input type="checkbox" id="followLatest"> Follow latest</label>
                <label class="check"><input type="checkbox" id="desktopNotifications"> Notify</label>
                <label class="check"><input type="checkbox" id="showFavoritesOnly"> Favorites only</label>
              </div>
              <div class="log-table-wrap">
                <table class="log-table">
                  <thead>
                    <tr>
                      <th style="width:10%">Fav</th>
                      <th style="width:18%">Character</th>
                      <th style="width:22%">Last Seen</th>
                      <th style="width:30%">Last Zone</th>
                      <th style="width:20%">Log</th>
                    </tr>
                  </thead>
                  <tbody id="logTableBody">
                    <tr><td class="log-empty" colspan="5">No logs loaded.</td></tr>
                  </tbody>
                </table>
              </div>
              <div class="row" style="margin-top:8px">
                <button class="secondary" onclick="refreshLogs()">Refresh</button>
                <button class="secondary" onclick="saveConfig()">Save</button>
              </div>
            </div>
          </details>
          <div class="panel">
            <div class="label-row">
              <span>DPS Parse</span>
              <span class="row" style="flex:0 0 auto">
                <button class="secondary small-btn" onclick="resetDps()">Reset</button>
              </span>
            </div>
            <div class="dps-controls">
              <div>
                <label>Filter</label>
                <select id="dpsFilterPreset">
                  <option value="current">Current</option>
                  <option value="all">All recent</option>
                  <option value="hour">Last hour</option>
                  <option value="day">Last day</option>
                  <option value="week">Last week</option>
                  <option value="custom">Custom</option>
                </select>
              </div>
              <div>
                <label>Encounter</label>
                <select id="dpsEncounterSelect"></select>
              </div>
              <div>
                <label>Start</label>
                <input id="dpsCustomStart" type="datetime-local">
              </div>
              <div>
                <label>End</label>
                <input id="dpsCustomEnd" type="datetime-local">
              </div>
              <div class="row" style="flex:0 0 auto">
                <button class="secondary small-btn" onclick="selectDps('prev')">Prev</button>
                <button class="secondary small-btn" onclick="selectDps('next')">Next</button>
              </div>
            </div>
            <div class="dps-summary">
              <div class="dps-stat"><strong id="dpsTarget">No target</strong><span>Target</span></div>
              <div class="dps-stat"><strong id="dpsDuration">00:00</strong><span>Duration</span></div>
              <div class="dps-stat"><strong id="dpsTotal">0</strong><span>Damage</span></div>
              <div class="dps-stat"><strong id="dpsTotalRate">0.00</strong><span>Raid DPS</span></div>
            </div>
            <table class="dps-table">
              <thead>
                <tr>
                  <th style="width:42%">Name</th>
                  <th style="width:20%">Damage</th>
                  <th style="width:18%">DPS</th>
                  <th style="width:20%">Hits</th>
                </tr>
              </thead>
              <tbody id="dpsRows">
                <tr><td colspan="4" class="log-empty">No damage parsed yet.</td></tr>
              </tbody>
            </table>
          </div>
          <div class="panel">
            <div class="label-row"><span>Last Log Line</span><span class="muted" id="lastLineStatus">Updated live</span></div>
            <div class="logline" id="lastLine">Waiting for new log lines.</div>
          </div>
        </div>
      </div>
    </section>

    <section class="tab-panel" id="tab-setup">
      <div class="settings-grid">
      <details class="panel" open>
        <summary>System</summary>
        <div class="panel-body">
          <label class="check"><input type="checkbox" id="launchAtStartup"> Launch EQ Watcher when the OS starts</label>
          <div class="muted" style="margin-top:8px">Starts automatically after you sign in to the desktop.</div>
          <label class="check" style="margin-top:12px"><input type="checkbox" id="automaticUpdateChecks"> Automatically check GitHub for updates</label>
          <div class="row" style="margin-top:8px">
            <button class="secondary" id="checkUpdateButton" onclick="checkForUpdates(true)">Check for updates</button>
            <button class="secondary" id="downloadUpdateButton" onclick="downloadUpdate()" hidden>Download update</button>
          </div>
          <div class="muted" id="updateStatus" style="margin-top:8px">EQ Watcher version __APP_VERSION__</div>
        </div>
      </details>

      <details class="panel" open>
        <summary>Overlays</summary>
        <div class="panel-body">
        <div class="checks">
          <label class="check"><input type="checkbox" id="nparseMapOverlayToggle"> Maps</label>
          <label class="check"><input type="checkbox" id="nparseClickThrough"> Maps click-through</label>
          <label class="check"><input type="checkbox" id="textOverlayToggle"> Text message</label>
          <label class="check"><input type="checkbox" id="textOverlayClickThrough"> Text click-through</label>
          <label class="check"><input type="checkbox" id="textOverlayEditFrame"> Text edit frame</label>
          <label class="check"><input type="checkbox" id="nparseSpellsOverlayToggle"> Spell timers</label>
          <label class="check"><input type="checkbox" id="nparseSpellsClickThrough"> Spell click-through</label>
          <label class="check"><input type="checkbox" id="rollOverlayToggle"> Roll leaders</label>
          <label class="check"><input type="checkbox" id="rollOverlayClickThrough"> Roll click-through</label>
          <label class="check"><input type="checkbox" id="frogOverlayToggle"> Dance character</label>
          <label class="check"><input type="checkbox" id="frogOverlayEditFrame"> Character edit frame</label>
          <label class="check"><input type="checkbox" id="chOverlayToggle"> CH chain</label>
          <label class="check"><input type="checkbox" id="chOverlayClickThrough"> CH click-through</label>
          <label class="check"><input type="checkbox" id="dpsOverlayToggle"> DPS parse</label>
          <label class="check"><input type="checkbox" id="dpsOverlayClickThrough"> DPS click-through</label>
          <label class="check"><input type="checkbox" id="aggroOverlayToggle"> Aggro meter</label>
          <label class="check"><input type="checkbox" id="aggroOverlayClickThrough"> Aggro click-through</label>
        </div>
        <label>Dance character</label>
        <select id="danceCharacter">
          <option value="all">All characters + moves</option>
          <option value="fussy">Fussy</option>
          <option value="enoent">Enoent</option>
          <option value="yellow_cap_frog">Groggie</option>
          <option value="rupert">Rupert</option>
          <option value="adventurer_frog">Adventurer Frog</option>
        </select>
        <label>Dance style</label>
        <select id="danceStyle">
          <option value="original">Original moves</option>
          <option value="new">New moves</option>
          <option value="adventurer" id="groggieAdventurerStyle">Adventurer Frog dance</option>
          <option value="special" id="characterSpecialStyle">Special move</option>
          <option value="bee_special" id="enoentBeeStyle">Enoent bumble bee butt-shake special</option>
          <option value="stinger_special" id="enoentStingerStyle">Enoent bumble bee stinger-shake special</option>
          <option value="combo">Combo cycle</option>
        </select>
        <div class="row" style="margin-top:10px">
          <label class="inline-field">DPS rows <input id="dpsOverlayRows" type="number" min="1" max="20"></label>
          <label class="inline-field">Cycle seconds <input id="dpsCycleSeconds" type="number" min="2" max="120"></label>
          <label class="inline-field">Text seconds <input id="textOverlayDuration" type="number" min="1" max="30"></label>
        </div>
        <label class="check" style="margin-top:10px"><input type="checkbox" id="dpsCycleEnabled"> Cycle DPS overlay</label>
        <label class="check" style="margin-top:10px"><input type="checkbox" id="textOverlayShowAll"> Show text for every trigger</label>
        </div>
      </details>

      <details class="panel" open>
        <summary>Audio Alerts</summary>
        <div class="panel-body">
        <div class="checks">
          <label class="check"><input type="checkbox" id="speak"> Speak</label>
          <label class="check"><input type="checkbox" id="beep"> Beep</label>
        </div>
        <div class="row" style="margin-top:8px">
          <button class="secondary" onclick="toggleVoice()">Toggle Voice</button>
          <button class="secondary" onclick="toggleBeep()">Toggle Beep</button>
        </div>
        <label>Voice</label>
        <select id="voiceType">
          <option value="">English US</option>
          <option value="en-us+m1">Male 1</option>
          <option value="en-us+m2">Male 2</option>
          <option value="en-us+m3">Male 3</option>
          <option value="en-us+m4">Male 4</option>
          <option value="en-us+f1">Female 1</option>
          <option value="en-us+f2">Female 2</option>
          <option value="en-us+f3">Female 3</option>
          <option value="en-us+f4">Female 4</option>
          <option value="en-us+croak">Croak</option>
          <option value="en-us+whisper">Whisper</option>
          <option value="en-us+klatt">Klatt</option>
          <option value="en-us+klatt2">Klatt 2</option>
          <option value="en-us+klatt3">Klatt 3</option>
          <option value="en-us+whisperf">Whisper Female</option>
        </select>
        <div class="row">
          <div>
            <label>Rate</label>
            <input id="voiceRate" type="number" min="-100" max="100">
          </div>
          <div>
            <label>Pitch</label>
            <input id="voicePitch" type="number" min="-100" max="100">
          </div>
        </div>
        <div class="volume-control">
          <div class="volume-head"><span>Voice volume</span><output id="voiceVolumeValue">100%</output></div>
          <input id="voiceVolume" type="range" min="0" max="100" step="1" value="100">
        </div>
        <div class="volume-control">
          <div class="volume-head"><span>Beep volume</span><output id="beepVolumeValue">100%</output></div>
          <input id="beepVolume" type="range" min="0" max="100" step="1" value="100">
        </div>
        <label>Beep melody</label>
        <select id="beepMelody">
          <optgroup label="EverQuest">
            <option value="eq_kelethin">Kelethin / Greater Faydark</option>
          </optgroup>
          <optgroup label="Chrono Trigger">
            <option value="chrono_600ad">600 A.D. / Wind Scene</option>
            <option value="chrono_theme">Chrono Trigger Theme</option>
            <option value="chrono_schala">Schala's Theme</option>
          </optgroup>
          <optgroup label="The Legend of Zelda: Ocarina of Time">
            <option value="zelda_oot_lost_woods">Lost Woods / Saria's Song</option>
            <option value="zelda_oot_song_of_storms">Song of Storms</option>
            <option value="zelda_oot_gerudo_valley">Gerudo Valley</option>
          </optgroup>
          <optgroup label="Final Fantasy">
            <option value="ff_prelude">Prelude</option>
            <option value="ff_victory">Victory Fanfare</option>
            <option value="ff5_main">Final Fantasy V Main Theme</option>
          </optgroup>
        </select>
        <label>Beep playback</label>
        <select id="beepPlayback">
          <option value="midi">Single MIDI note</option>
          <option value="musical3">Musical three-note phrase</option>
          <option value="musical">Musical four-note phrase</option>
          <option value="musical8">Full musical bar (eight notes)</option>
          <option value="original_bar">Original-timing MIDI measure</option>
        </select>
        <div class="row" style="margin-top:10px">
          <button class="secondary" onclick="testVoice()">Test Voice</button>
          <button class="secondary" onclick="testBeep()">Test Beep</button>
        </div>
        </div>
      </details>
      </div>
    </section>

    <section class="tab-panel" id="tab-triggers">
      <div class="settings-grid">
      <details class="panel" open>
        <summary>New Trigger</summary>
        <div class="panel-body">
        <label>Trigger name</label>
        <input id="name" placeholder="Complete Heal">
        <label>Regex pattern</label>
        <textarea id="pattern" placeholder="Soandso begins casting Complete Healing"></textarea>
        <label>Alert text</label>
        <input id="message" placeholder="Complete heal incoming">
        <label>Display text</label>
        <input id="displayText" placeholder="Mob has been slowed!">
        <label class="check" style="margin-top:10px"><input type="checkbox" id="useTextOverlay"> Show in text overlay</label>
        <div class="row">
          <div>
            <label>Timer seconds</label>
            <input id="timer" type="number" min="0" value="0">
          </div>
          <div>
            <label>Timer action</label>
            <select id="timerAction">
              <option value="start">Start timer</option>
              <option value="stop">Stop timer</option>
            </select>
          </div>
          <div>
            <label>Stop target</label>
            <input id="timerTarget" placeholder="Invisibility">
          </div>
          <div>
            <label>Color</label>
            <input id="color" type="color" value="#60a5fa">
          </div>
        </div>
        <button class="full-width secondary" style="margin-top:10px" onclick="addTrigger()">Add Trigger</button>
        </div>
      </details>

      <details class="panel" open>
        <summary>Import</summary>
        <div class="panel-body">
        <label>GINA import package</label>
        <select id="ginaPackageSelect"></select>
        <button class="full-width" onclick="importGinaPackage()">Import Package</button>
        </div>
      </details>
      </div>
      <div class="panel">
        <div class="section-header">
          <div>
            <h2>Trigger Library</h2>
            <div class="muted">Enable, inspect, and prune imported triggers quickly.</div>
          </div>
          <div class="actions">
            <button class="secondary" onclick="saveConfig()">Save</button>
          </div>
        </div>
        <div class="trigger-tools">
          <input id="triggerSearch" placeholder="Filter triggers">
          <button class="secondary" onclick="renderTriggers()">Filter</button>
        </div>
        <div class="trigger-list">
          <div class="trigger-head"><span></span><span>Name</span><span>Alert message</span><span>Timer</span><span>Actions</span></div>
          <div id="triggers"></div>
        </div>
      </div>
    </section>

    <section class="tab-panel library" id="tab-spellbook">
      <div class="panel">
        <div class="section-header">
          <div>
            <h2>Spellbook checklist</h2>
            <div class="muted">Compare an EverQuest <code>/outputfile spellbook</code> export with the P99 Wiki class list.</div>
          </div>
          <a id="spellbookWikiLink" href="https://p99wiki.eqgeeks.org/Necromancer" target="_blank" rel="noopener">Open class wiki</a>
        </div>
        <div class="spellbook-toolbar">
          <label>Character
            <input id="spellbookCharacter" list="spellbookCharacters" placeholder="Active character">
            <datalist id="spellbookCharacters"></datalist>
          </label>
          <label>Spellbook export
            <input id="spellbookFile" list="spellbookFiles" placeholder="Auto-detect or enter path">
            <datalist id="spellbookFiles"></datalist>
          </label>
          <label>Class
            <select id="spellbookClass"><option value="">Auto-detect</option></select>
          </label>
          <label>Level
            <input id="spellbookLevel" type="number" min="1" max="60" placeholder="Auto">
          </label>
          <button class="primary" id="spellbookRefresh" onclick="refreshSpellbook()">Scan</button>
        </div>
        <div class="spellbook-path" id="spellbookHint">Run <code>/outputfile spellbook</code> in EverQuest, then click Scan.</div>
      </div>
      <div id="spellbookResults"><div class="empty">No spellbook has been scanned yet.</div></div>
    </section>

    <section class="tab-panel library" id="tab-inventory">
      <div class="panel">
        <div class="section-header">
          <div>
            <h2>Inventory exports</h2>
            <div class="muted">Inventory files created by EverQuest's <code>/outputfile inventory</code> command.</div>
          </div>
        </div>
        <div class="inventory-toolbar">
          <label>Search items
            <input id="inventorySearch" type="search" placeholder="Item name, ID, location, or character">
          </label>
          <label>Character
            <select id="inventoryCharacter"><option value="">All characters</option></select>
          </label>
          <label class="check"><input type="checkbox" id="inventoryRaidOnly"> Common raid items only</label>
          <button class="primary" id="inventoryRefresh" onclick="refreshInventory()">Refresh</button>
        </div>
        <div class="spellbook-path" id="inventoryHint">All characters are shown. “Common raid items” uses EQCM's default Raid Kit list.</div>
      </div>
      <div id="inventoryResults"><div class="empty">No inventory exports loaded yet.</div></div>
    </section>

    <section class="tab-panel library" id="tab-maps">
      <div class="panel nparse-card">
        <div class="panel-title">
          <span>Maps</span>
          <button class="secondary" onclick="refreshNParse()">Refresh</button>
        </div>
        <div class="map-toolbar">
          <div>
            <label>Zone</label>
            <select id="nparseZoneSelect"></select>
          </div>
          <div>
            <label>Opacity %</label>
            <input id="nparseOpacity" type="number" min="0" max="100">
          </div>
          <div class="checks" style="grid-template-columns:repeat(4,minmax(0,1fr)); margin-top:0">
            <label class="check"><input type="checkbox" id="nparseAutoFollow"> Auto follow</label>
            <label class="check"><input type="checkbox" id="nparseCenterCharacter"> Center on character</label>
            <label class="check"><input type="checkbox" id="nparseShowGrid"> Grid</label>
            <label class="check"><input type="checkbox" id="nparseShowPoi"> POI</label>
          </div>
        </div>
        <div class="map-frame">
          <svg id="nparseMap" viewBox="0 0 100 100" preserveAspectRatio="xMidYMid meet"></svg>
        </div>
        <div class="nparse-info">
          <span id="nparseZoneLabel">No zone selected</span>
          <span id="nparseMapMeta"></span>
        </div>
      </div>
      <div class="panel">
        <div class="panel-title">
          <span>Zone Timers</span>
          <button class="secondary" onclick="startZoneTimer()">Start</button>
        </div>
        <div id="nparseTimers" class="mini-list"></div>
        <div class="muted" id="nparseTimersHint" style="margin-top:8px"></div>
      </div>
      <div class="panel">
        <div class="panel-title">
          <span>CH Chain</span>
          <button class="secondary" onclick="saveConfig()">Save</button>
        </div>
        <div class="grid two">
          <label>Filter
            <select id="chChainFilterMode">
              <option value="recent_current_or_guild">Current log 5m + guild</option>
              <option value="recent_current_only">Current log recent only</option>
              <option value="guild_only">Guild chat only</option>
              <option value="guild_style">Guild style</option>
              <option value="gg_style">GG style</option>
              <option value="ca_style">CA style</option>
              <option value="la_style">LA style</option>
              <option value="tagged_styles">GG/CA/LA styles</option>
              <option value="all_current_log">All current log CH</option>
            </select>
          </label>
          <label>Recent seconds
            <input type="number" id="chChainRecentSeconds" min="30" max="3600" step="30">
          </label>
        </div>
      </div>
    </section>
    </div>
  </main>
<script>
(() => {
  const channelName = "linux-gina-ui";
  const params = new URLSearchParams(window.location.search);
  const duplicateOpen = params.get("reuse") === "1";
  if (!("BroadcastChannel" in window)) return;

  const channel = new BroadcastChannel(channelName);
  const instanceId = `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  let existingTabAnswered = false;

  channel.onmessage = (event) => {
    const message = event.data || {};
    if (message.instanceId === instanceId) return;
    if (message.type === "linux-gina-open-request") {
      channel.postMessage({type: "linux-gina-open-response", instanceId});
      if (!duplicateOpen) window.location.reload();
    } else if (duplicateOpen && message.type === "linux-gina-open-response") {
      existingTabAnswered = true;
      window.close();
      setTimeout(() => {
        document.body.innerHTML = "";
      }, 150);
    }
  };

  if (duplicateOpen) {
    channel.postMessage({type: "linux-gina-open-request", instanceId});
    setTimeout(() => {
      if (!existingTabAnswered) {
        history.replaceState(null, "", window.location.pathname);
      }
    }, 500);
  }
})();

let config = null;
let alerts = [];
let activeTimers = [];
let scoutTimerState = null;
let ring8TimerState = null;
let nparseState = null;
let dpsState = null;
let spellbookDiscovery = null;
let inventoryLoaded = false;
let inventoryData = null;
let latestUpdate = null;
let lastNparseZone = "";
let lastNparseLocation = "";
const LOG_STALE_SECONDS = 7 * 24 * 60 * 60;
let logRefreshPending = null;

function fmt(seconds) {
  seconds = Math.max(0, Math.ceil(seconds));
  const m = String(Math.floor(seconds / 60)).padStart(2, "0");
  const s = String(seconds % 60).padStart(2, "0");
  return `${m}:${s}`;
}

function fmtLong(seconds) {
  seconds = Math.max(0, Math.ceil(seconds));
  const h = Math.floor(seconds / 3600);
  const m = String(Math.floor((seconds % 3600) / 60)).padStart(2, "0");
  const s = String(seconds % 60).padStart(2, "0");
  return h ? `${h}:${m}:${s}` : `${m}:${s}`;
}

function describeActiveLog(path, character) {
  const name = path ? String(path).split(/[\\/]/).pop() : "";
  const parts = [];
  if (name) parts.push(name);
  if (character) parts.push(character);
  return parts.length ? parts.join(" · ") : "No active log";
}

async function refreshSpellbookDiscovery() {
  spellbookDiscovery = await api("/api/spellbook/files");
  const characterInput = document.getElementById("spellbookCharacter");
  const characterList = document.getElementById("spellbookCharacters");
  const fileList = document.getElementById("spellbookFiles");
  const classSelect = document.getElementById("spellbookClass");
  const storedCharacter = localStorage.getItem("eq-watcher-spellbook-character") || "";
  const storedPath = localStorage.getItem("eq-watcher-spellbook-path") || "";
  if (!characterInput.value) characterInput.value = storedCharacter || spellbookDiscovery.active_character || "";
  if (!document.getElementById("spellbookFile").value) document.getElementById("spellbookFile").value = storedPath;
  characterList.innerHTML = (spellbookDiscovery.characters || [])
    .map(name => `<option value="${escapeHtml(name)}"></option>`).join("");
  fileList.innerHTML = (spellbookDiscovery.files || [])
    .map(file => `<option value="${escapeHtml(file.path)}">${escapeHtml(file.character || file.name)}</option>`).join("");
  const previousClass = classSelect.value;
  classSelect.innerHTML = `<option value="">Auto-detect</option>` + (spellbookDiscovery.classes || [])
    .map(name => `<option value="${escapeHtml(name)}">${escapeHtml(name)}</option>`).join("");
  if ((spellbookDiscovery.classes || []).includes(previousClass)) classSelect.value = previousClass;
  return spellbookDiscovery;
}

function spellChips(names, missing = false) {
  if (!names?.length) return `<span class="muted">None</span>`;
  return names.map(name => `<span class="spell-chip${missing ? " missing" : ""}">${escapeHtml(name)}</span>`).join("");
}

function renderSpellbook(result) {
  const root = document.getElementById("spellbookResults");
  const hint = document.getElementById("spellbookHint");
  if (!result.ready) {
    hint.textContent = result.message || "No spellbook export found.";
    root.innerHTML = `<div class="empty">${escapeHtml(result.message || "No spellbook export found.")}</div>`;
    return;
  }
  const levelText = result.character_level
    ? `${result.character_level} (${result.level_source === "log" ? "from log" : result.level_source === "manual" ? "manual" : "inferred"})`
    : "Unknown";
  hint.textContent = `${result.path}${result.character_log ? ` · level read from ${result.character_log}` : ""}`;
  const wikiLink = document.getElementById("spellbookWikiLink");
  wikiLink.href = result.wiki_url || "https://p99wiki.eqgeeks.org/";
  root.innerHTML = `
    <div class="spellbook-summary">
      <div class="spellbook-stat"><strong>${escapeHtml(result.character || "Unknown")}</strong><span>Character</span></div>
      <div class="spellbook-stat"><strong>${escapeHtml(result.class_name)}</strong><span>Class</span></div>
      <div class="spellbook-stat"><strong>${escapeHtml(levelText)}</strong><span>Character level</span></div>
      <div class="spellbook-stat"><strong>${result.owned_count} / ${result.eligible_total}</strong><span>Eligible spells owned</span></div>
    </div>
    <div class="label-row"><span>${result.missing_count} missing · ${result.recognized_count} exported spell names recognized</span><span>Wiki catalog ${escapeHtml((result.catalog_generated_at || "").slice(0, 10))}</span></div>
    <div class="spell-levels">
      ${(result.levels || []).map(row => `
        <section class="spell-level">
          <div class="spell-level-head">
            <strong>Level ${row.level} ${row.complete ? '<span class="spell-complete">✓ Complete</span>' : ""}</strong>
            <a href="${escapeHtml(row.wiki_url)}" target="_blank" rel="noopener">P99 Wiki level ${row.level}</a>
          </div>
          <div class="spell-columns">
            <div class="spell-column"><h3>Owned (${row.owned.length})</h3><div class="spell-list">${spellChips(row.owned)}</div></div>
            <div class="spell-column"><h3>Missing (${row.missing.length})</h3><div class="spell-list">${spellChips(row.missing, true)}</div></div>
          </div>
        </section>`).join("")}
    </div>`;
}

async function refreshSpellbook() {
  const button = document.getElementById("spellbookRefresh");
  button.disabled = true;
  button.textContent = "Scanning…";
  try {
    await refreshSpellbookDiscovery();
    const character = document.getElementById("spellbookCharacter").value.trim();
    const path = document.getElementById("spellbookFile").value.trim();
    const className = document.getElementById("spellbookClass").value;
    const level = document.getElementById("spellbookLevel").value;
    localStorage.setItem("eq-watcher-spellbook-character", character);
    localStorage.setItem("eq-watcher-spellbook-path", path);
    const params = new URLSearchParams({character, path, class: className, level});
    const result = await api(`/api/spellbook?${params}`);
    renderSpellbook(result);
  } catch (error) {
    document.getElementById("spellbookResults").innerHTML = `<div class="empty">${escapeHtml(String(error.message || error))}</div>`;
  } finally {
    button.disabled = false;
    button.textContent = "Scan";
  }
}

function renderInventory() {
  if (!inventoryData) return;
  const query = document.getElementById("inventorySearch").value.trim().toLowerCase();
  const character = document.getElementById("inventoryCharacter").value;
  const raidOnly = document.getElementById("inventoryRaidOnly").checked;
  const allItems = inventoryData.items || [];
  const rows = allItems.filter(item => {
    if (character && item.character !== character) return false;
    if (raidOnly && !item.raid_kit) return false;
    if (!query) return true;
    return [item.character, item.location, item.name, item.id, item.count, item.slots]
      .some(value => String(value || "").toLowerCase().includes(query));
  }).sort((a, b) => a.character.localeCompare(b.character) || a.location.localeCompare(b.location) || a.name.localeCompare(b.name));
  const inventories = inventoryData.inventories || [];
  const raidCount = allItems.filter(item => item.raid_kit).length;
  const root = document.getElementById("inventoryResults");
  root.innerHTML = `
    <div class="inventory-summary">
      <span class="pill"><strong>${inventories.length}</strong>&nbsp; character${inventories.length === 1 ? "" : "s"}</span>
      <span class="pill"><strong>${rows.length}</strong>&nbsp; of ${allItems.length} items shown</span>
      <span class="pill"><strong>${raidCount}</strong>&nbsp; common raid-kit matches</span>
    </div>
    ${rows.length ? `<div class="inventory-table-wrap"><table class="inventory-table">
      <thead><tr><th>Character</th><th>Location</th><th>Name</th><th>ID</th><th>Count</th><th>Slots</th><th>Raid Kit</th></tr></thead>
      <tbody>${rows.map(item => `<tr>
        <td>${escapeHtml(item.character)}</td><td>${escapeHtml(item.location)}</td><td>${escapeHtml(item.name)}</td>
        <td>${escapeHtml(item.id)}</td><td>${escapeHtml(item.count)}</td><td>${escapeHtml(item.slots)}</td>
        <td>${item.raid_kit ? '<span class="spell-chip">Common</span>' : ''}</td>
      </tr>`).join("")}</tbody>
    </table></div>` : `<div class="empty">No items match the current filters.</div>`}`;
}

async function refreshInventory() {
  const button = document.getElementById("inventoryRefresh");
  const characterSelect = document.getElementById("inventoryCharacter");
  const previousCharacter = characterSelect.value;
  button.disabled = true;
  button.textContent = "Refreshing…";
  try {
    inventoryData = await api("/api/inventory");
    const inventories = inventoryData.inventories || [];
    const characters = inventories.map(row => row.character).sort((a, b) => a.localeCompare(b));
    characterSelect.innerHTML = `<option value="">All characters</option>` + characters
      .map(name => `<option value="${escapeHtml(name)}">${escapeHtml(name)}</option>`).join("");
    if (characters.includes(previousCharacter)) characterSelect.value = previousCharacter;
    const hint = document.getElementById("inventoryHint");
    if (!inventories.length) {
      hint.innerHTML = `No inventory exports found. Run <code>/outputfile inventory</code> in EverQuest, then click Refresh.`;
      document.getElementById("inventoryResults").innerHTML = `<div class="empty">No <code>*-Inventory.txt</code> files were found beside a known EverQuest Logs folder.</div>`;
      inventoryLoaded = true;
      return;
    }
    hint.textContent = `Showing the newest export for each character from ${inventoryData.files.length} discovered files. Common raid items use EQCM's default Raid Kit.`;
    renderInventory();
    inventoryLoaded = true;
  } catch (error) {
    document.getElementById("inventoryResults").innerHTML = `<div class="empty">${escapeHtml(String(error.message || error))}</div>`;
  } finally {
    button.disabled = false;
    button.textContent = "Refresh";
  }
}

async function api(path, options) {
  const res = await fetch(path, options);
  if (!res.ok) throw new Error(await res.text());
  return await res.json();
}

async function checkForUpdates(force = false) {
  const button = document.getElementById("checkUpdateButton");
  const status = document.getElementById("updateStatus");
  const download = document.getElementById("downloadUpdateButton");
  button.disabled = true;
  status.textContent = "Checking GitHub releases…";
  try {
    latestUpdate = await api(`/api/update?force=${force ? "1" : "0"}`);
    download.hidden = !latestUpdate.update_available;
    if (!latestUpdate.ok) {
      status.textContent = `Version ${latestUpdate.current_version} · update check unavailable: ${latestUpdate.error || "unknown error"}`;
    } else if (latestUpdate.update_available) {
      status.textContent = `Version ${latestUpdate.latest_version} is available (installed: ${latestUpdate.current_version}).`;
    } else {
      status.textContent = `EQ Watcher ${latestUpdate.current_version} is up to date.`;
    }
  } catch (error) {
    status.textContent = `Update check failed: ${String(error.message || error)}`;
  } finally {
    button.disabled = false;
  }
}

function downloadUpdate() {
  const url = latestUpdate?.download_url || latestUpdate?.release_url;
  if (url) window.open(url, "_blank", "noopener");
}

async function load() {
  config = await api("/api/config");
  const nparse = config.nparse || {};
  const nparseMaps = nparse.maps || {};
  const textOverlay = nparse.text_overlay || {};
  const chChain = nparse.ch_chain || {};
  const nparseSpells = nparse.nparse_spells || {};
  const rollOverlay = nparse.rolls || {};
  const frogOverlay = nparse.frog_dancer || {};
  const dpsOverlay = nparse.dps || {};
  const aggroOverlay = nparse.aggro || {};
  document.getElementById("logDir").value = config.log_dir;
  document.getElementById("followLatest").checked = config.follow_latest;
  document.getElementById("showFavoritesOnly").checked = config.show_favorites_only ?? false;
  document.getElementById("speak").checked = config.speak;
  document.getElementById("beep").checked = config.beep;
  document.getElementById("voiceType").value = config.voice_type || "";
  document.getElementById("voiceRate").value = config.voice_rate ?? 0;
  document.getElementById("voicePitch").value = config.voice_pitch ?? 0;
  document.getElementById("voiceVolume").value = config.voice_volume ?? 100;
  document.getElementById("beepVolume").value = config.beep_volume ?? 100;
  document.getElementById("beepMelody").value = config.beep_melody || "chrono_600ad";
  document.getElementById("beepPlayback").value = config.beep_playback || "midi";
  updateVolumeReadouts();
  document.getElementById("desktopNotifications").checked = config.desktop_notifications;
  document.getElementById("launchAtStartup").checked = config.launch_at_startup ?? false;
  document.getElementById("automaticUpdateChecks").checked = config.automatic_update_checks ?? false;
  if (config.automatic_update_checks) checkForUpdates(false);
  document.getElementById("nparseZoneSelect").value = nparseMaps.selected_zone || "";
  document.getElementById("nparseAutoFollow").checked = nparseMaps.auto_follow ?? true;
  document.getElementById("nparseCenterCharacter").checked = nparseMaps.center_character_location ?? false;
  document.getElementById("nparseShowGrid").checked = nparseMaps.show_grid ?? true;
  document.getElementById("nparseShowPoi").checked = nparseMaps.show_poi ?? true;
  document.getElementById("nparseMapOverlayToggle").checked = nparseMaps.toggled ?? false;
  document.getElementById("nparseClickThrough").checked = nparseMaps.clickthrough ?? false;
  document.getElementById("textOverlayToggle").checked = textOverlay.toggled ?? true;
  document.getElementById("textOverlayClickThrough").checked = textOverlay.clickthrough ?? true;
  document.getElementById("textOverlayEditFrame").checked = !(textOverlay.frameless ?? true);
  document.getElementById("textOverlayDuration").value = textOverlay.duration_seconds ?? 4;
  document.getElementById("textOverlayShowAll").checked = textOverlay.show_all_triggers ?? false;
  syncTextOverlayEditFrame();
  document.getElementById("nparseSpellsOverlayToggle").checked = nparseSpells.toggled ?? false;
  document.getElementById("nparseSpellsClickThrough").checked = nparseSpells.clickthrough ?? false;
  document.getElementById("rollOverlayToggle").checked = rollOverlay.toggled ?? true;
  document.getElementById("rollOverlayClickThrough").checked = rollOverlay.clickthrough ?? true;
  document.getElementById("frogOverlayToggle").checked = frogOverlay.toggled ?? true;
  document.getElementById("frogOverlayEditFrame").checked = !(frogOverlay.frameless ?? true);
  document.getElementById("danceCharacter").value = frogOverlay.character || "yellow_cap_frog";
  document.getElementById("danceStyle").value = frogOverlay.dance_style || "new";
  syncDanceStyleOptions();
  document.getElementById("nparseOpacity").value = nparseMaps.opacity ?? 80;
  document.getElementById("chChainFilterMode").value = chChain.filter_mode || (chChain.guild_only ? "guild_only" : "recent_current_or_guild");
  document.getElementById("chChainRecentSeconds").value = chChain.recent_seconds ?? 300;
  document.getElementById("chOverlayToggle").checked = chChain.toggled ?? false;
  document.getElementById("chOverlayClickThrough").checked = chChain.clickthrough ?? true;
  document.getElementById("dpsOverlayToggle").checked = dpsOverlay.toggled ?? false;
  document.getElementById("dpsOverlayClickThrough").checked = dpsOverlay.clickthrough ?? true;
  document.getElementById("dpsOverlayRows").value = dpsOverlay.max_rows ?? 10;
  document.getElementById("dpsFilterPreset").value = dpsOverlay.filter_preset || "all";
  document.getElementById("dpsCustomStart").value = tsToLocalInput(dpsOverlay.custom_start_ts || 0);
  document.getElementById("dpsCustomEnd").value = tsToLocalInput(dpsOverlay.custom_end_ts || 0);
  document.getElementById("dpsCycleEnabled").checked = dpsOverlay.cycle_enabled ?? false;
  document.getElementById("dpsCycleSeconds").value = dpsOverlay.cycle_seconds ?? 8;
  document.getElementById("aggroOverlayToggle").checked = aggroOverlay.toggled ?? true;
  document.getElementById("aggroOverlayClickThrough").checked = aggroOverlay.clickthrough ?? true;
  document.getElementById("activeLogSummary").textContent = describeActiveLog(config.active_log, "");
  updateRuntimeToggles();
  await refreshLogs();
  await refreshGinaPackages();
  await refreshNParse();
  renderTriggers();
  renderAlerts();
  renderTimers();
  await refreshDps();
}

async function refreshScoutTimer(force = false) {
  try {
    scoutTimerState = await api(`/api/scout-timer${force ? "?refresh=1" : ""}`);
  } catch (error) {
    scoutTimerState = {ok:false, error:String(error)};
  }
  renderScoutTimer();
}

function renderScoutTimer() {
  const root = document.getElementById("scoutTimer");
  if (!root) return;
  if (!scoutTimerState?.ok) {
    root.innerHTML = `<div class="empty">Scout timer unavailable${scoutTimerState?.error ? `: ${escapeHtml(scoutTimerState.error)}` : "."}</div>`;
    return;
  }

  const due = Number(scoutTimerState.display_timestamp || scoutTimerState.timestamp || 0) * 1000;
  if (!due || Number.isNaN(due)) {
    root.innerHTML = `<div class="empty">Scout timer returned an invalid date.</div>`;
    return;
  }
  const remaining = (due - Date.now()) / 1000;
  const exactTime = new Date(due).toLocaleString();
  const derivedGuess = !!scoutTimerState.derived_guess;
  const badgeText = derivedGuess ? "Next guess" : (scoutTimerState.guess ? "Estimate" : "Tracked");
  const badge = `<span class="scout-badge">${badgeText}</span>`;
  const stale = scoutTimerState.stale ? " · showing cached result" : "";
  root.innerHTML = `
    <div class="scout-card">
      <span class="timer-strip"></span>
      <div>
        <div class="timer-name">${escapeHtml(scoutTimerState.name || "Scout Charisa")}${badge}</div>
        <div class="scout-meta">${escapeHtml(exactTime)}${escapeHtml(stale)}</div>
      </div>
      <div class="scout-countdown">
        <span class="timer-time">${fmtLong(remaining)}</span>
        <span class="scout-state">${derivedGuess ? "Until guessed spawn" : "Until spawn"}</span>
      </div>
    </div>`;
}

async function refreshRing8Timer() {
  try {
    ring8TimerState = await api("/api/ring8-timer");
  } catch (error) {
    ring8TimerState = {ok:false, error:String(error)};
  }
  renderRing8Timer();
}

function ring8ErrorMessage(error) {
  const message = String(error || "").replace(/^Error:\s*/, "");
  try {
    return JSON.parse(message).error || message;
  } catch (_) {
    return message;
  }
}

async function setRing8Timer() {
  const input = document.getElementById("ring8Input");
  const errorRoot = document.getElementById("ring8Error");
  errorRoot.textContent = "";
  try {
    ring8TimerState = await api("/api/ring8-timer", {
      method:"POST",
      body:JSON.stringify({time: input.value}),
    });
    config = await api("/api/config");
    renderRing8Timer();
  } catch (error) {
    errorRoot.textContent = ring8ErrorMessage(error);
  }
}

async function clearRing8Timer() {
  const errorRoot = document.getElementById("ring8Error");
  errorRoot.textContent = "";
  try {
    ring8TimerState = await api("/api/ring8-timer", {
      method:"POST",
      body:JSON.stringify({clear:true}),
    });
    config = await api("/api/config");
    document.getElementById("ring8Input").value = "";
    renderRing8Timer();
  } catch (error) {
    errorRoot.textContent = ring8ErrorMessage(error);
  }
}

function renderRing8Timer() {
  const root = document.getElementById("ring8Timer");
  const input = document.getElementById("ring8Input");
  if (!root || !input) return;
  if (!ring8TimerState?.active) {
    root.innerHTML = `<div class="empty">No Ring 8 roll time set.</div>`;
    return;
  }
  if (document.activeElement !== input && !input.value) {
    input.value = ring8TimerState.input || "";
  }
  const due = Number(ring8TimerState.timestamp || 0) * 1000;
  if (!due || Number.isNaN(due)) {
    root.innerHTML = `<div class="empty">Ring 8 timer has an invalid date.</div>`;
    return;
  }
  const remaining = (due - Date.now()) / 1000;
  const exactTime = new Intl.DateTimeFormat([], {
    timeZone: ring8TimerState.timezone || "America/New_York",
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZoneName: "short",
  }).format(new Date(due));
  root.innerHTML = `
    <div class="scout-card ring8-card">
      <span class="timer-strip"></span>
      <div>
        <div class="timer-name">Ring 8 Roll<span class="scout-badge">Eastern</span></div>
        <div class="scout-meta">${escapeHtml(exactTime)}</div>
      </div>
      <div class="scout-countdown">
        <span class="timer-time">${remaining > 0 ? fmtLong(remaining) : "00:00"}</span>
        <span class="scout-state">${remaining > 0 ? "Until roll" : "Roll time passed"}</span>
      </div>
    </div>`;
}

async function refreshLogs() {
  const logs = await api("/api/logs?dir=" + encodeURIComponent(document.getElementById("logDir").value));
  const select = document.getElementById("activeLogSelect");
  const tableBody = document.getElementById("logTableBody");
  const favorites = favoriteCharacterSet();
  const showFavoritesOnly = document.getElementById("showFavoritesOnly").checked;
  select.innerHTML = "";
  tableBody.innerHTML = "";
  if (!logs.length) {
    tableBody.innerHTML = `<tr><td class="log-empty" colspan="5">No logs found in this folder.</td></tr>`;
    return;
  }
  let rendered = 0;
  for (const log of logs) {
    const character = log.character || "Unknown";
    const favoriteKey = normalizeCharacterName(character);
    const isFavorite = favorites.has(favoriteKey);
    const lastSeen = Number(log.last_seen || 0);
    const isStale = !lastSeen || ((Date.now() / 1000) - lastSeen > LOG_STALE_SECONDS);
    const option = document.createElement("option");
    option.value = log.path;
    option.textContent = log.name;
    if (log.active || log.path === config.active_log) option.selected = true;
    select.appendChild(option);

    if (showFavoritesOnly && !isFavorite) continue;
    const row = document.createElement("tr");
    row.classList.toggle("is-active", Boolean(log.active) || log.path === config.active_log);
    row.classList.toggle("is-stale", isStale);
    row.innerHTML = `
      <td class="favorite-cell"><input type="checkbox" title="Favorite ${escapeHtml(character)}" ${isFavorite ? "checked" : ""}></td>
      <td class="log-character">${escapeHtml(character)}</td>
      <td class="log-seen">${escapeHtml(formatLogTimestamp(lastSeen))}${isStale ? '<span class="log-stale-badge" title="No zone event has been logged for more than 7 days">Stale</span>' : ''}</td>
      <td class="log-zone">${escapeHtml(log.last_zone || "Unknown")}</td>
      <td class="log-name" title="${escapeHtml(log.name)}">${escapeHtml(log.name)}</td>`;
    row.querySelector("input").addEventListener("change", async (event) => {
      await setFavoriteCharacter(character, event.target.checked);
    });
    tableBody.appendChild(row);
    rendered += 1;
  }
  if (!rendered) {
    tableBody.innerHTML = `<tr><td class="log-empty" colspan="5">No favorite characters found in this folder.</td></tr>`;
  }
}

function scheduleLogRefresh(delay = 250) {
  if (logRefreshPending !== null) clearTimeout(logRefreshPending);
  logRefreshPending = setTimeout(async () => {
    logRefreshPending = null;
    await refreshLogs();
  }, delay);
}

function normalizeCharacterName(value) {
  return String(value || "").trim().toLowerCase();
}

function favoriteCharacterSet() {
  return new Set((config?.favorite_characters || []).map(normalizeCharacterName).filter(Boolean));
}

async function setFavoriteCharacter(character, favorite) {
  const name = String(character || "").trim();
  if (!name) return;
  const favorites = favoriteCharacterSet();
  const key = normalizeCharacterName(name);
  if (favorite) favorites.add(key);
  else favorites.delete(key);
  const displayNames = new Map((config?.favorite_characters || []).map(value => [normalizeCharacterName(value), value]));
  displayNames.set(key, name);
  config.favorite_characters = Array.from(favorites).sort().map(value => displayNames.get(value) || value);
  config = await api("/api/config", {method:"POST", body:JSON.stringify(collectConfig())});
  await refreshLogs();
}

async function refreshGinaPackages() {
  const packages = await api("/api/gina-packages");
  const select = document.getElementById("ginaPackageSelect");
  select.innerHTML = "";
  for (const pkg of packages) {
    const option = document.createElement("option");
    option.value = pkg.path;
    option.textContent = pkg.name;
    select.appendChild(option);
  }
}

async function refreshNParse() {
  nparseState = await api("/api/nparse");
  renderNParse();
}

function renderNParse() {
  const select = document.getElementById("nparseZoneSelect");
  const zones = [...(nparseState?.zones || [])];
  const currentZone = nparseState?.zone || config?.nparse?.maps?.selected_zone || "";
  if (currentZone && !zones.some(zone => zone.label === currentZone)) {
    zones.unshift({label: currentZone});
  }
  select.innerHTML = "";
  for (const zone of zones) {
    const option = document.createElement("option");
    option.value = zone.label || "";
    option.textContent = zone.label || "";
    select.appendChild(option);
  }
  if (currentZone) select.value = currentZone;
  const zoneLabel = document.getElementById("nparseZoneLabel");
  const mapMeta = document.getElementById("nparseMapMeta");
  const timersHint = document.getElementById("nparseTimersHint");
  const map = nparseState?.map || {};
  const zoneTimer = nparseState?.zone_timer || {};
  zoneLabel.textContent = nparseState?.zone_label || currentZone || "No zone selected";
  mapMeta.textContent = map.source ? map.source.split("/").pop() : "No map loaded";
  timersHint.textContent = zoneTimer.duration_text ? `Zone respawn: ${zoneTimer.duration_text}` : "No zone respawn timer found.";
  renderNParseMap();
  renderNParseTimers();
}

function rgbaFromRgb(rgb, alpha) {
  const [r, g, b] = Array.isArray(rgb) ? rgb : [255, 255, 255];
  return `rgba(${r},${g},${b},${alpha})`;
}

function headingToBearing(heading) {
  const text = String(heading || "").trim().toLowerCase().replace(/\s+/g, " ");
  const headings = {
    "north": 0,
    "north by northeast": 22.5,
    "northeast": 45,
    "east by northeast": 67.5,
    "east": 90,
    "east by southeast": 112.5,
    "southeast": 135,
    "south by southeast": 157.5,
    "south": 180,
    "south by southwest": 202.5,
    "southwest": 225,
    "west by southwest": 247.5,
    "west": 270,
    "west by northwest": 292.5,
    "northwest": 315,
    "north by northwest": 337.5,
  };
  return Object.prototype.hasOwnProperty.call(headings, text) ? headings[text] : null;
}

function playerArrowSvg(x, y, heading, movementAngle) {
  const bearing = headingToBearing(heading);
  const hasMovementAngle = Number.isFinite(Number(movementAngle));
  if (!hasMovementAngle && bearing === null) {
    return [
      `<circle cx="${x}" cy="${y}" r="7" fill="none" stroke="#f5d44f" stroke-width="3" vector-effect="non-scaling-stroke"/>`,
      `<circle cx="${x}" cy="${y}" r="2.5" fill="#f5d44f" vector-effect="non-scaling-stroke"/>`,
    ].join("");
  }
  const angle = hasMovementAngle ? Number(movementAngle) : (bearing - 90) * Math.PI / 180;
  const size = 13;
  const tail = 8;
  const halfWidth = 6;
  const tip = [x + Math.cos(angle) * size, y + Math.sin(angle) * size];
  const back = [x - Math.cos(angle) * tail, y - Math.sin(angle) * tail];
  const left = [back[0] + Math.cos(angle - Math.PI / 2) * halfWidth, back[1] + Math.sin(angle - Math.PI / 2) * halfWidth];
  const right = [back[0] + Math.cos(angle + Math.PI / 2) * halfWidth, back[1] + Math.sin(angle + Math.PI / 2) * halfWidth];
  const points = [tip, left, right].map(point => point.join(",")).join(" ");
  return [
    `<polygon points="${points}" fill="#f5d44f" stroke="rgba(18,22,26,0.86)" stroke-width="2" vector-effect="non-scaling-stroke"/>`,
    `<circle cx="${x}" cy="${y}" r="2.5" fill="rgba(18,22,26,0.86)" vector-effect="non-scaling-stroke"/>`,
  ].join("");
}

function renderNParseMap() {
  const svg = document.getElementById("nparseMap");
  const map = nparseState?.map || {};
  const opacity = Math.max(0, Math.min(100, Number(nparseState?.maps_config?.opacity ?? 80))) / 100;
  const showGrid = !!nparseState?.maps_config?.show_grid;
  const showPoi = !!nparseState?.maps_config?.show_poi;
  if (!map.lines?.length && !map.points?.length) {
    svg.innerHTML = `<text x="10" y="24" fill="#9aa7b2">No map data available for this zone.</text>`;
    return;
  }
  const bounds = map.bounds || {min_x: 0, min_y: 0, max_x: 100, max_y: 100};
  const pad = Math.max(12, Math.min(80, Math.round(Math.max(bounds.max_x - bounds.min_x, bounds.max_y - bounds.min_y) * 0.05)));
  const minX = bounds.min_x - pad;
  const minY = bounds.min_y - pad;
  const maxX = bounds.max_x + pad;
  const maxY = bounds.max_y + pad;
  const width = Math.max(1, maxX - minX);
  const height = Math.max(1, maxY - minY);
  const centerCharacter = !!nparseState?.maps_config?.center_character_location;
  const locationX = Number(nparseState?.location_x);
  const locationY = Number(nparseState?.location_y);
  const useCenter = centerCharacter && Number.isFinite(locationX) && Number.isFinite(locationY);
  const viewMinX = useCenter ? locationX - (width / 2) : minX;
  const viewMinY = useCenter ? locationY - (height / 2) : minY;
  const gridStep = width > 1600 || height > 1600 ? 200 : 100;
  const gridColor = rgbaFromRgb([90, 167, 255], 0.16);
  const lines = [];
  if (showGrid) {
    const startX = Math.floor(viewMinX / gridStep) * gridStep;
    const endX = Math.ceil((viewMinX + width) / gridStep) * gridStep;
    const startY = Math.floor(viewMinY / gridStep) * gridStep;
    const endY = Math.ceil((viewMinY + height) / gridStep) * gridStep;
    for (let x = startX; x <= endX; x += gridStep) {
      lines.push(`<line x1="${x}" y1="${viewMinY}" x2="${x}" y2="${viewMinY + height}" stroke="${gridColor}" stroke-width="1" vector-effect="non-scaling-stroke"/>`);
    }
    for (let y = startY; y <= endY; y += gridStep) {
      lines.push(`<line x1="${viewMinX}" y1="${y}" x2="${viewMinX + width}" y2="${y}" stroke="${gridColor}" stroke-width="1" vector-effect="non-scaling-stroke"/>`);
    }
  }
  for (const line of map.lines || []) {
    lines.push(`<line x1="${line.x1}" y1="${line.y1}" x2="${line.x2}" y2="${line.y2}" stroke="${rgbaFromRgb(line.color, opacity)}" stroke-width="1.2" vector-effect="non-scaling-stroke"/>`);
  }
  if (showPoi) {
    for (const point of map.points || []) {
      lines.push(`<circle cx="${point.x}" cy="${point.y}" r="${Math.max(2, Math.min(6, point.size || 3))}" fill="${rgbaFromRgb(point.color, Math.min(1, opacity + 0.1))}" stroke="rgba(0,0,0,0.35)" stroke-width="1" vector-effect="non-scaling-stroke"/>`);
      if (point.label) {
        lines.push(`<text x="${point.x + 4}" y="${point.y - 4}" fill="#dbeafe" font-size="10">${escapeHtml(point.label)}</text>`);
      }
    }
  }
  if (Number.isFinite(locationX) && Number.isFinite(locationY)) {
    const heading = (nparseState?.heading || "").trim();
    const markerLabel = heading ? `YOU ${escapeHtml(heading)}` : "YOU";
    lines.push(playerArrowSvg(locationX, locationY, heading, nparseState?.movement_angle));
    lines.push(`<text x="${locationX + 8}" y="${locationY - 10}" fill="#f5d44f" font-size="11">${markerLabel}</text>`);
  }
  svg.setAttribute("viewBox", `${viewMinX} ${viewMinY} ${width} ${height}`);
  svg.innerHTML = lines.join("");
}

function renderNParseTimers() {
  const root = document.getElementById("nparseTimers");
  const zoneTimer = nparseState?.zone_timer || {};
  const zoneName = nparseState?.zone_label || nparseState?.zone || "Current zone";
  const enteredAt = Number(nparseState?.entered_at || 0) * 1000;
  root.innerHTML = "";
  const zoneSeconds = Number(zoneTimer.duration_seconds || 0);
  const presets = Array.isArray(nparseState?.custom_timers) ? nparseState.custom_timers : [];
  if (zoneSeconds > 0) {
    const remaining = Math.max(0, zoneSeconds - ((Date.now() - enteredAt) / 1000));
    const row = document.createElement("div");
    row.className = "mini-row";
    row.innerHTML = `
      <div>
        <div class="mini-name">${escapeHtml(zoneName)} Respawn</div>
        <div class="mini-meta">${escapeHtml(zoneTimer.duration_text || "")}</div>
      </div>
      <div class="timer-time">${fmt(remaining)}</div>
      <button class="secondary small-btn">Start</button>`;
    row.querySelector("button").onclick = startZoneTimer;
    root.appendChild(row);
  }
  for (const preset of presets) {
    if (!Array.isArray(preset) || preset.length < 3) continue;
    const [name, triggerText, durationText] = preset;
    const row = document.createElement("div");
    row.className = "mini-row";
    row.innerHTML = `
      <div>
        <div class="mini-name">${escapeHtml(name || "Timer")}</div>
        <div class="mini-meta">${escapeHtml(triggerText || "")} · ${escapeHtml(durationText || "")}</div>
      </div>
      <div class="mini-meta">${escapeHtml(durationText || "")}</div>
      <button class="secondary small-btn">Start</button>`;
    row.querySelector("button").onclick = () => startPresetTimer(preset);
    root.appendChild(row);
  }
  if (!zoneSeconds && !presets.length) {
    root.innerHTML = `<div class="empty">No timers configured.</div>`;
  }
}

async function startTimerPayload(payload) {
  if (!payload || !payload.timer_seconds) return;
  await api("/api/nparse/start", {method:"POST", body:JSON.stringify(payload)});
}

async function startZoneTimer() {
  const timer = nparseState?.zone_timer || {};
  const seconds = Number(timer.duration_seconds || 0);
  if (!seconds) return;
  await startTimerPayload({
    name: `${nparseState?.zone_label || nparseState?.zone || "Zone"} Respawn`,
    message: `${nparseState?.zone_label || nparseState?.zone || "Zone"} respawn`,
    timer_seconds: seconds,
    color: "#f5d44f",
  });
}

async function startPresetTimer(preset) {
  if (!Array.isArray(preset) || preset.length < 3) return;
  const [name, triggerText, durationText] = preset;
  const seconds = Number(durationText ? durationText.split(":").reduce((total, part) => total * 60 + Number(part || 0), 0) : 0);
  if (!seconds) return;
  await startTimerPayload({
    name: name || "Timer",
    message: triggerText || name || "Timer",
    timer_seconds: seconds,
    color: "#60a5fa",
  });
}

async function clearOverlayTimer(timer) {
  const id = String(timer?.id || "").trim();
  const triggerId = String(timer?.trigger_id || "").trim();
  if (!id) return;
  await api("/api/overlay/clear-timer", {
    method:"POST",
    body:JSON.stringify({id, trigger_id:triggerId}),
  });
  activeTimers = activeTimers.filter(timer => String(timer.id || "") !== id);
  renderTimers();
}

async function clearActiveTimers() {
  await api("/api/overlay/clear-timers", {method:"POST", body:"{}"});
  activeTimers = [];
  renderTimers();
}

async function clearRolls() {
  await api("/api/overlay/clear-rolls", {method:"POST", body:"{}"});
}

function formatNumber(value) {
  return new Intl.NumberFormat().format(Number(value || 0));
}

function tsToLocalInput(value) {
  const ts = Number(value || 0);
  if (!ts) return "";
  const date = new Date(ts * 1000);
  if (Number.isNaN(date.getTime())) return "";
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
  return local.toISOString().slice(0, 16);
}

function localInputToTs(value) {
  const text = String(value || "").trim();
  if (!text) return 0;
  const date = new Date(text);
  return Number.isNaN(date.getTime()) ? 0 : Math.floor(date.getTime() / 1000);
}

async function refreshDps() {
  dpsState = await api("/api/dps");
  renderDps();
}

async function resetDps() {
  const result = await api("/api/dps/reset", {method:"POST"});
  dpsState = result.dps || null;
  renderDps();
}

async function selectDps(direction, encounterId) {
  const result = await api("/api/dps/select", {
    method:"POST",
    body:JSON.stringify({direction, encounter_id: encounterId || ""}),
  });
  dpsState = result.dps || null;
  config = await api("/api/config");
  renderDps();
}

function collectConfig() {
  return {
    ...config,
    log_dir: document.getElementById("logDir").value,
    active_log: document.getElementById("activeLogSelect").value,
    follow_latest: document.getElementById("followLatest").checked,
    favorite_characters: config?.favorite_characters || [],
    show_favorites_only: document.getElementById("showFavoritesOnly").checked,
    speak: document.getElementById("speak").checked,
    voice_type: document.getElementById("voiceType").value,
    voice_rate: Number(document.getElementById("voiceRate").value || 0),
    voice_pitch: Number(document.getElementById("voicePitch").value || 0),
    voice_volume: Number(document.getElementById("voiceVolume").value || 0),
    beep: document.getElementById("beep").checked,
    beep_volume: Number(document.getElementById("beepVolume").value || 0),
    beep_melody: document.getElementById("beepMelody").value,
    beep_playback: document.getElementById("beepPlayback").value,
    desktop_notifications: document.getElementById("desktopNotifications").checked,
    launch_at_startup: document.getElementById("launchAtStartup").checked,
    automatic_update_checks: document.getElementById("automaticUpdateChecks").checked,
    overlay: {
      ...((config && config.overlay) || {}),
      enabled: false,
      click_through: false,
    },
    nparse: {
      discord: {
        ...((config && config.nparse && config.nparse.discord) || {}),
      },
      maps: {
        ...((config && config.nparse && config.nparse.maps) || {}),
        selected_zone: document.getElementById("nparseZoneSelect").value,
        auto_follow: document.getElementById("nparseAutoFollow").checked,
        center_character_location: document.getElementById("nparseCenterCharacter").checked,
        toggled: document.getElementById("nparseMapOverlayToggle").checked,
        clickthrough: document.getElementById("nparseClickThrough").checked,
        show_grid: document.getElementById("nparseShowGrid").checked,
        show_poi: document.getElementById("nparseShowPoi").checked,
        opacity: Number(document.getElementById("nparseOpacity").value === "" ? 80 : document.getElementById("nparseOpacity").value),
      },
      text_overlay: {
        ...((config && config.nparse && config.nparse.text_overlay) || {}),
        toggled: document.getElementById("textOverlayToggle").checked,
        frameless: !document.getElementById("textOverlayEditFrame").checked,
        clickthrough: document.getElementById("textOverlayEditFrame").checked ? false : document.getElementById("textOverlayClickThrough").checked,
        duration_seconds: Math.max(1, Math.min(30, Number(document.getElementById("textOverlayDuration").value || 4))),
        show_all_triggers: document.getElementById("textOverlayShowAll").checked,
      },
      nparse_spells: {
        ...((config && config.nparse && config.nparse.nparse_spells) || {}),
        toggled: document.getElementById("nparseSpellsOverlayToggle").checked,
        clickthrough: document.getElementById("nparseSpellsClickThrough").checked,
      },
      rolls: {
        ...((config && config.nparse && config.nparse.rolls) || {}),
        toggled: document.getElementById("rollOverlayToggle").checked,
        clickthrough: document.getElementById("rollOverlayClickThrough").checked,
      },
      frog_dancer: {
        ...((config && config.nparse && config.nparse.frog_dancer) || {}),
        toggled: document.getElementById("frogOverlayToggle").checked,
        character: document.getElementById("danceCharacter").value,
        dance_style: document.getElementById("danceStyle").value,
        frameless: !document.getElementById("frogOverlayEditFrame").checked,
        clickthrough: !document.getElementById("frogOverlayEditFrame").checked,
      },
      ch_chain: {
        ...((config && config.nparse && config.nparse.ch_chain) || {}),
        toggled: document.getElementById("chOverlayToggle").checked,
        clickthrough: document.getElementById("chOverlayClickThrough").checked,
        filter_mode: document.getElementById("chChainFilterMode").value,
        guild_only: document.getElementById("chChainFilterMode").value === "guild_only",
        recent_seconds: Number(document.getElementById("chChainRecentSeconds").value || 300),
      },
      dps: {
        ...((config && config.nparse && config.nparse.dps) || {}),
        toggled: document.getElementById("dpsOverlayToggle").checked,
        clickthrough: document.getElementById("dpsOverlayClickThrough").checked,
        max_rows: Math.max(1, Math.min(20, Number(document.getElementById("dpsOverlayRows").value || 10))),
        filter_preset: document.getElementById("dpsFilterPreset").value,
        custom_start_ts: localInputToTs(document.getElementById("dpsCustomStart").value),
        custom_end_ts: localInputToTs(document.getElementById("dpsCustomEnd").value),
        cycle_enabled: document.getElementById("dpsCycleEnabled").checked,
        cycle_seconds: Math.max(2, Math.min(120, Number(document.getElementById("dpsCycleSeconds").value || 8))),
      },
      aggro: {
        ...((config && config.nparse && config.nparse.aggro) || {}),
        toggled: document.getElementById("aggroOverlayToggle").checked,
        clickthrough: document.getElementById("aggroOverlayClickThrough").checked,
      },
      spells: {
        ...((config && config.nparse && config.nparse.spells) || {}),
        toggled: false,
        clickthrough: false,
        show_clear_buttons: false,
      },
    },
  };
}

async function saveConfig() {
  config = await api("/api/config", {method:"POST", body:JSON.stringify(collectConfig())});
  await refreshLogs();
  await refreshNParse();
  renderTriggers();
}

async function saveNParseConfig() {
  config = await api("/api/config", {method:"POST", body:JSON.stringify(collectConfig())});
  await refreshNParse();
  await refreshDps();
}

function updateRuntimeToggles() {
  document.getElementById("speak").checked = !!config?.speak;
  document.getElementById("beep").checked = !!config?.beep;
}

function updateVolumeReadouts() {
  document.getElementById("voiceVolumeValue").textContent = `${document.getElementById("voiceVolume").value}%`;
  document.getElementById("beepVolumeValue").textContent = `${document.getElementById("beepVolume").value}%`;
}

function syncTextOverlayEditFrame() {
  const editFrame = document.getElementById("textOverlayEditFrame").checked;
  const clickThrough = document.getElementById("textOverlayClickThrough");
  if (editFrame) clickThrough.checked = false;
  clickThrough.disabled = editFrame;
}

function syncDanceStyleOptions() {
  const character = document.getElementById("danceCharacter").value;
  const isAllCharacters = character === "all";
  const specialLabels = {
    fussy: "Fussy Snorkel Surf special",
    enoent: "Enoent moonwalk special",
    yellow_cap_frog: "Groggie breakdance special",
    rupert: "Rupert headbanging special",
  };
  const specialLabel = specialLabels[character] || "";
  const special = document.getElementById("characterSpecialStyle");
  special.textContent = specialLabel || "Special move";
  special.disabled = isAllCharacters || !specialLabel;
  special.hidden = isAllCharacters || !specialLabel;
  const beeSpecial = document.getElementById("enoentBeeStyle");
  const isEnoent = character === "enoent";
  beeSpecial.disabled = !isEnoent;
  beeSpecial.hidden = !isEnoent;
  const stingerSpecial = document.getElementById("enoentStingerStyle");
  stingerSpecial.disabled = !isEnoent;
  stingerSpecial.hidden = !isEnoent;
  const adventurer = document.getElementById("groggieAdventurerStyle");
  const isGroggie = character === "yellow_cap_frog";
  adventurer.disabled = isAllCharacters || !isGroggie;
  adventurer.hidden = isAllCharacters || !isGroggie;
  const selectedStyle = document.getElementById("danceStyle");
  selectedStyle.disabled = isAllCharacters;
  if ((!specialLabel && selectedStyle.value === "special") || (!isGroggie && selectedStyle.value === "adventurer") || (!isEnoent && ["bee_special", "stinger_special"].includes(selectedStyle.value))) {
    selectedStyle.value = "new";
  }
}

async function toggleVoice() {
  config = await api("/api/toggle-voice", {method:"POST"});
  updateRuntimeToggles();
}

async function toggleBeep() {
  config = await api("/api/toggle-beep", {method:"POST"});
  updateRuntimeToggles();
}

function bindNParseAutosave() {
  const ids = [
    "nparseZoneSelect",
    "nparseAutoFollow",
    "nparseCenterCharacter",
    "nparseMapOverlayToggle",
    "nparseClickThrough",
    "textOverlayToggle",
    "textOverlayClickThrough",
    "textOverlayEditFrame",
    "textOverlayDuration",
    "textOverlayShowAll",
    "nparseSpellsOverlayToggle",
    "nparseSpellsClickThrough",
    "rollOverlayToggle",
    "rollOverlayClickThrough",
    "frogOverlayToggle",
    "frogOverlayEditFrame",
    "danceStyle",
    "nparseShowGrid",
    "nparseShowPoi",
    "nparseOpacity",
    "chOverlayToggle",
    "chOverlayClickThrough",
    "dpsOverlayToggle",
    "dpsOverlayClickThrough",
    "dpsOverlayRows",
    "dpsFilterPreset",
    "dpsCustomStart",
    "dpsCustomEnd",
    "dpsCycleEnabled",
    "dpsCycleSeconds",
    "aggroOverlayToggle",
    "aggroOverlayClickThrough",
    "launchAtStartup",
    "automaticUpdateChecks",
  ];
  for (const id of ids) {
    const el = document.getElementById(id);
    el.addEventListener("change", saveNParseConfig);
  }
  document.getElementById("textOverlayEditFrame").addEventListener("change", syncTextOverlayEditFrame);
  document.getElementById("danceCharacter").addEventListener("change", () => {
    syncDanceStyleOptions();
    saveNParseConfig();
  });
  document.getElementById("dpsEncounterSelect").addEventListener("change", ev => selectDps("pick", ev.target.value));
}

function renderTriggers() {
  const root = document.getElementById("triggers");
  root.innerHTML = "";
  const needle = (document.getElementById("triggerSearch")?.value || "").trim().toLowerCase();
  for (const trigger of config.triggers) {
    const haystack = Object.values(trigger).map(value => String(value ?? "")).join(" ").toLowerCase();
    if (needle && !haystack.includes(needle)) continue;
    const action = (trigger.timer_action || "start").toLowerCase();
    const alertMessage = trigger.message || trigger.name || "Trigger";
    const displayMessage = trigger.use_text
      ? (trigger.display_text || alertMessage)
      : "Off";
    const spokenMessage = trigger.voice_text || alertMessage;
    const timerLabel = action === "stop"
      ? `stop ${trigger.timer_target || trigger.timer_name || trigger.name || ""}`.trim()
      : (trigger.dynamic_timer ? "dynamic" : `${trigger.timer_seconds || 0}s`);
    const timerDetails = action === "stop"
      ? `Stop timer: ${trigger.timer_target || trigger.timer_name || trigger.name || "unspecified"}`
      : (trigger.dynamic_timer
          ? `Start dynamic timer${trigger.timer_name ? `: ${trigger.timer_name}` : ""}`
          : (Number(trigger.timer_seconds || 0) > 0
              ? `Start ${trigger.timer_seconds}s timer: ${trigger.timer_name || alertMessage}`
              : "No timer"));
    const reminderDetails = Number(trigger.reminder_after_seconds || 0) > 0
      ? `After ${trigger.reminder_after_seconds}s: ${trigger.reminder_message || trigger.reminder_name || "Reminder"}${trigger.reminder_display_text ? ` · Display: ${trigger.reminder_display_text}` : ""}`
      : "Off";
    const behaviorDetails = [
      `Enabled: ${trigger.enabled ? "Yes" : "No"}`,
      `Text overlay: ${trigger.use_text ? "On" : "Off"}`,
      `Voice flag: ${trigger.use_voice ? "On" : "Off"}`,
      `Stack timers: ${trigger.stack_timers ? "On" : "Off"}`,
      `Ignore if running: ${trigger.ignore_if_running ? "On" : "Off"}`,
    ].join(" · ");
    const originDetails = [
      trigger.source ? `Source: ${trigger.source}` : "Source: Local",
      trigger.group ? `Group: ${trigger.group}` : "",
      trigger.category ? `Category: ${trigger.category}` : "",
    ].filter(Boolean).join(" · ");
    const detail = (label, value, classes = "") => `
      <div class="trigger-detail ${classes}">
        <div class="trigger-detail-label">${escapeHtml(label)}</div>
        <div class="trigger-detail-value ${classes.includes("code") ? "code" : ""}">${escapeHtml(String(value || "—"))}</div>
      </div>`;
    const item = document.createElement("div");
    item.className = "trigger-card";
    item.innerHTML = `
      <div class="trigger-item">
        <span class="swatch" style="background:${escapeHtml(trigger.color || "#60a5fa")}"></span>
        <span class="trigger-name">${escapeHtml(trigger.name || "Unnamed trigger")}</span>
        <span class="trigger-message">${escapeHtml(alertMessage)}</span>
        <span class="muted trigger-timer-summary">${escapeHtml(timerLabel)}</span>
        <span class="row trigger-actions"><input type="checkbox" aria-label="Enabled" ${trigger.enabled ? "checked" : ""}><button class="danger small-btn">Delete</button></span>
      </div>
      <details class="trigger-details">
        <summary>Messages &amp; settings</summary>
        <div class="trigger-detail-grid">
          ${detail("Alert message", alertMessage, "wide")}
          ${detail("Text overlay message", displayMessage)}
          ${detail("Spoken message", spokenMessage)}
          ${detail("Reminder", reminderDetails)}
          ${detail("Trigger pattern", trigger.pattern || "—", "wide code")}
          ${detail("Timer", timerDetails)}
          ${detail("Color", trigger.color || "#60a5fa")}
          ${detail("Behavior", behaviorDetails, "wide")}
          ${detail("Origin", originDetails, "wide")}
        </div>
      </details>`;
    const del = item.querySelector(".danger");
    const checkbox = item.querySelector('input[type="checkbox"]');
    checkbox.onchange = async () => {
      trigger.enabled = checkbox.checked;
      await saveConfig();
    };
    del.onclick = async () => {
      config.triggers = config.triggers.filter(t => t.id !== trigger.id);
      await saveConfig();
    };
    root.appendChild(item);
  }
}

async function addTrigger() {
  const trigger = {
    id: crypto.randomUUID(),
    name: document.getElementById("name").value || "New Trigger",
    pattern: document.getElementById("pattern").value,
    message: document.getElementById("message").value || document.getElementById("name").value || "Trigger",
    display_text: document.getElementById("displayText").value || document.getElementById("message").value || document.getElementById("name").value || "Trigger",
    timer_seconds: Number(document.getElementById("timer").value || 0),
    timer_action: document.getElementById("timerAction").value || "start",
    timer_target: document.getElementById("timerTarget").value || "",
    color: document.getElementById("color").value,
    enabled: true,
    use_text: document.getElementById("useTextOverlay").checked,
  };
  config.triggers.push(trigger);
  await saveConfig();
}

async function testAlert() {
  await api("/api/test", {method:"POST", body:JSON.stringify({message:"Test alert", display_message:"Test text overlay", use_text:true, timer_seconds:10, color:"#60a5fa"})});
}

async function testVoice() {
  config = await api("/api/config", {method:"POST", body:JSON.stringify(collectConfig())});
  await api("/api/speak", {method:"POST", body:JSON.stringify({text:"EQ Watcher voice test"})});
}

async function testBeep() {
  config = await api("/api/config", {method:"POST", body:JSON.stringify(collectConfig())});
  await api("/api/beep", {method:"POST", body:"{}"});
}

async function importGinaPackage() {
  const path = document.getElementById("ginaPackageSelect").value;
  if (!path) return;
  const result = await api("/api/import-gina", {method:"POST", body:JSON.stringify({path})});
  config = await api("/api/config");
  renderTriggers();
  alert(`Imported ${result.imported} triggers. Skipped ${result.skipped.length}.`);
}

function speak(text) {
  if (!config?.speak) return;
  fetch("/api/speak", {method:"POST", body:JSON.stringify({text})});
}

function beep() {
  if (!config?.beep) return;
  const AudioContext = window.AudioContext || window.webkitAudioContext;
  if (!AudioContext) return;
  const ctx = new AudioContext();
  const osc = ctx.createOscillator();
  const gain = ctx.createGain();
  osc.frequency.value = 880;
  gain.gain.value = 0.08;
  osc.connect(gain);
  gain.connect(ctx.destination);
  osc.start();
  setTimeout(() => { osc.stop(); ctx.close(); }, 160);
}

function normalizeTimerTarget(hit) {
  return String(hit?.timer_target || hit?.timer_name || hit?.name || hit?.message || "").trim().toLowerCase();
}

function timerMatchesTarget(timer, triggerId, target) {
  const normalizedTarget = String(target || "").trim().toLowerCase();
  if (triggerId && String(timer.trigger_id || "").trim() === String(triggerId).trim()) return true;
  if (!normalizedTarget) return false;
  const keys = [
    timer.trigger_id,
    timer.timer_name,
    timer.name,
    timer.message,
  ].map(value => String(value || "").trim().toLowerCase());
  return keys.includes(normalizedTarget);
}

function addAlert(hit) {
  hit.created = Date.now();
  if ((hit.timer_action || "start") === "stop") {
    const target = normalizeTimerTarget(hit);
    activeTimers = activeTimers.filter(timer => !timerMatchesTarget(timer, hit.trigger_id, target));
  } else if (hit.timer_seconds > 0) {
    const timerAlreadyRunning = hit.ignore_if_running && activeTimers.some(timer =>
      timer.trigger_id === hit.trigger_id && Number(timer.ends || 0) > Date.now()
    );
    if (!timerAlreadyRunning) {
      hit.ends = Date.now() + hit.timer_seconds * 1000;
      if (!hit.stack_timers) {
        activeTimers = activeTimers.filter(timer => timer.trigger_id !== hit.trigger_id);
      }
      activeTimers.unshift(hit);
    }
  }
  alerts.unshift(hit);
  alerts = alerts.slice(0, 20);
  if (config.desktop_notifications && Notification.permission === "granted") {
    new Notification(hit.name, {body: hit.message});
  }
  renderAlerts();
  renderTimers();
}

function clearAlerts() {
  alerts = [];
  renderAlerts();
}

function renderAlerts() {
  const root = document.getElementById("alerts");
  root.innerHTML = "";
  document.getElementById("alertCount").textContent = alerts.length;
  if (!alerts.length) {
    root.innerHTML = `<div class="empty">No alerts yet.</div>`;
    return;
  }
  for (const alert of alerts) {
    const card = document.createElement("div");
    card.className = "alert";
    const remaining = alert.ends ? (alert.ends - Date.now()) / 1000 : 0;
    card.innerHTML = `
      <span class="swatch" style="background:${escapeHtml(alert.color || "#60a5fa")}"></span>
      <div>
        <h2>${escapeHtml(alert.message)}</h2>
        <div class="alert-meta">${escapeHtml(alert.name || "Trigger")}</div>
      </div>
      <div class="alert-time">${alert.ends ? fmt(remaining) : ""}</div>
      <div class="logline">${escapeHtml(alert.line || "")}</div>`;
    root.appendChild(card);
  }
}

function renderTimers() {
  const root = document.getElementById("timers");
  activeTimers = activeTimers.filter(timer => !timer.ends || timer.ends > Date.now());
  root.innerHTML = "";
  document.getElementById("timerCount").textContent = activeTimers.length;
  if (!activeTimers.length) {
    root.innerHTML = `<div class="empty">No active timers.</div>`;
    return;
  }
  for (const timer of activeTimers) {
    const remaining = (timer.ends - Date.now()) / 1000;
    const row = document.createElement("div");
    row.className = "timer-row";
    row.innerHTML = `
      <span class="timer-strip" style="background:${escapeHtml(timer.color || "#60a5fa")}"></span>
      <span class="timer-name">${escapeHtml(timer.timer_name || timer.message || timer.name || "Timer")}</span>
      <span class="timer-time">${fmt(remaining)}</span>`;
    const btn = document.createElement("button");
    btn.className = "secondary timer-clear";
    btn.textContent = "Clear";
    btn.title = "Clear timer";
    btn.onclick = () => clearOverlayTimer(timer);
    row.appendChild(btn);
    root.appendChild(row);
  }
}

function renderDps() {
  const target = dpsState?.target || "";
  const rows = Array.isArray(dpsState?.rows) ? dpsState.rows : [];
  const encounters = Array.isArray(dpsState?.encounters) ? dpsState.encounters : [];
  const selectedId = dpsState?.selected_encounter_id || dpsState?.encounter_id || "";
  const encounterSelect = document.getElementById("dpsEncounterSelect");
  encounterSelect.innerHTML = "";
  if (!encounters.length) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "No recent encounters";
    encounterSelect.appendChild(option);
  } else {
    for (const encounter of encounters) {
      const option = document.createElement("option");
      option.value = encounter.encounter_id || "";
      const status = encounter.active ? "live" : formatLogTimestamp(encounter.last_ts || encounter.start_ts || 0);
      option.textContent = `${encounter.target || "Unknown"} · ${status} · ${fmt(encounter.duration || 0)} · ${formatNumber(encounter.total_damage || 0)}`;
      if (option.value === selectedId) option.selected = true;
      encounterSelect.appendChild(option);
    }
  }
  document.getElementById("dpsTarget").textContent = target || "No target";
  document.getElementById("dpsDuration").textContent = fmt(Number(dpsState?.duration || 0));
  document.getElementById("dpsTotal").textContent = formatNumber(dpsState?.total_damage || 0);
  document.getElementById("dpsTotalRate").textContent = Number(dpsState?.total_dps || 0).toFixed(2);
  const body = document.getElementById("dpsRows");
  body.innerHTML = "";
  if (!rows.length) {
    body.innerHTML = `<tr><td colspan="4" class="log-empty">No damage parsed yet.</td></tr>`;
    return;
  }
  rows.forEach((row, index) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td class="dps-name" title="${escapeHtml(row.name || "")}">${index + 1}. ${escapeHtml(row.name || "")}</td>
      <td>${formatNumber(row.damage || 0)}</td>
      <td>${Number(row.dps || 0).toFixed(2)}</td>
      <td>${formatNumber(row.hits || 0)}</td>`;
    body.appendChild(tr);
  });
}

function escapeHtml(s) {
  return String(s || "").replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

function formatLogTimestamp(value) {
  const ts = Number(value || 0);
  if (!ts) return "Unknown";
  const date = new Date(ts * 1000);
  if (Number.isNaN(date.getTime())) return "Unknown";
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function connectEvents() {
  const events = new EventSource("/events");
  events.onmessage = (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.kind === "trigger") addAlert(msg.payload);
    if (msg.kind === "status") {
      document.getElementById("watching").textContent = msg.payload.message;
      const activeLogText = describeActiveLog(msg.payload.active_log || "", msg.payload.character || "");
      document.getElementById("activeLog").textContent = activeLogText;
      document.getElementById("activeLogSummary").textContent = activeLogText;
      if (typeof msg.payload.speak === "boolean" || typeof msg.payload.beep === "boolean") {
        config = {...config, ...(msg.payload.speak !== undefined ? {speak: msg.payload.speak} : {}), ...(msg.payload.beep !== undefined ? {beep: msg.payload.beep} : {})};
        updateRuntimeToggles();
      }
      if (msg.payload.zone && msg.payload.zone !== lastNparseZone) {
        lastNparseZone = msg.payload.zone;
        refreshNParse();
        scheduleLogRefresh();
      }
    }
    if (msg.kind === "line") document.getElementById("lastLine").textContent = msg.payload.line;
    if (msg.kind === "dps") {
      refreshDps();
    }
  };
}

function initTabs() {
  const buttons = Array.from(document.querySelectorAll(".tab-button"));
  const panels = Array.from(document.querySelectorAll(".tab-panel"));
  const activate = (name) => {
    for (const button of buttons) {
      const active = button.dataset.tab === name;
      button.classList.toggle("active", active);
      button.setAttribute("aria-selected", active ? "true" : "false");
    }
    for (const panel of panels) {
      panel.classList.toggle("active", panel.id === `tab-${name}`);
    }
    localStorage.setItem("linux-gina-tab", name);
    if (name === "spellbook" && !spellbookDiscovery) refreshSpellbook();
    if (name === "inventory" && !inventoryLoaded) refreshInventory();
  };
  for (const button of buttons) {
    button.type = "button";
    button.setAttribute("role", "tab");
    button.addEventListener("click", () => activate(button.dataset.tab));
  }
  const saved = localStorage.getItem("linux-gina-tab");
  if (buttons.some(button => button.dataset.tab === saved)) activate(saved);
}

setInterval(() => { renderAlerts(); renderTimers(); renderScoutTimer(); renderRing8Timer(); }, 500);
setInterval(() => refreshScoutTimer(), 60 * 1000);
setInterval(() => refreshRing8Timer(), 60 * 1000);
setInterval(async () => {
  const state = await api("/api/state");
  document.getElementById("lastLine").textContent = state.last_line || "Waiting for new log lines.";
  const activeLogText = describeActiveLog(state.active_log || "", state.character || "");
  document.getElementById("activeLog").textContent = activeLogText;
  document.getElementById("activeLogSummary").textContent = activeLogText;
  const nextZone = state.nparse?.zone || "";
  const nextLocation = [state.nparse?.location_x, state.nparse?.location_y, state.nparse?.location_z, state.nparse?.movement_angle].join("|");
  dpsState = state.dps || dpsState;
  renderDps();
  if (nextZone !== lastNparseZone || nextLocation !== lastNparseLocation) {
    lastNparseZone = nextZone;
    lastNparseLocation = nextLocation;
    await refreshNParse();
  }
}, 1500);

document.getElementById("logDir").addEventListener("change", refreshLogs);
document.getElementById("activeLogSelect").addEventListener("change", saveConfig);
document.getElementById("followLatest").addEventListener("change", saveConfig);
document.getElementById("showFavoritesOnly").addEventListener("change", saveConfig);
document.getElementById("triggerSearch").addEventListener("input", renderTriggers);
document.getElementById("desktopNotifications").addEventListener("change", () => {
  if (document.getElementById("desktopNotifications").checked && Notification.permission === "default") Notification.requestPermission();
});
document.getElementById("ring8Input").addEventListener("keydown", event => {
  if (event.key === "Enter") setRing8Timer();
});
for (const id of ["voiceVolume", "beepVolume"]) {
  document.getElementById(id).addEventListener("input", updateVolumeReadouts);
  document.getElementById(id).addEventListener("change", saveConfig);
}
document.getElementById("beepMelody").addEventListener("change", saveConfig);
document.getElementById("beepPlayback").addEventListener("change", saveConfig);
for (const id of ["spellbookCharacter", "spellbookFile", "spellbookLevel"]) {
  document.getElementById(id).addEventListener("keydown", event => {
    if (event.key === "Enter") refreshSpellbook();
  });
}
document.getElementById("spellbookCharacter").addEventListener("change", () => {
  document.getElementById("spellbookFile").value = "";
});
document.getElementById("inventorySearch").addEventListener("input", renderInventory);
document.getElementById("inventoryCharacter").addEventListener("change", renderInventory);
document.getElementById("inventoryRaidOnly").addEventListener("change", renderInventory);

initTabs();
// Keep the remote read-only timer independent of config, logs, maps, and DPS
// startup. A failure in another panel must not leave Scout stuck on "Loading".
refreshScoutTimer();
refreshRing8Timer();
load().then(() => {
  bindNParseAutosave();
  connectEvents();
});
</script>
</body>
</html>
""".replace("__APP_VERSION__", APP_VERSION)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        return

    def _send(self, status=HTTPStatus.OK, content_type="application/json"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def _json(self, data, status=HTTPStatus.OK):
        body = json.dumps(data).encode("utf-8")
        self._send(status)
        self.wfile.write(body)

    def _body(self):
        length = int(self.headers.get("Content-Length", "0"))
        if not length:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._send(content_type="text/html; charset=utf-8")
            self.wfile.write(HTML.encode("utf-8"))
            return
        if parsed.path == "/api/ping":
            self._json({"ok": True, "app": "eq-watcher", "url": STATE.get("ui_url", "")})
            return
        if parsed.path == "/api/open-ui":
            controller = OVERLAY_CONTROLLER
            if controller is not None:
                controller.open_ui()
            else:
                url = STATE.get("ui_url", "")
                if url:
                    webbrowser.open_new_tab(f"{url}?reuse=1")
            self._json({"ok": True})
            return
        if parsed.path == "/api/config":
            with CONFIG_LOCK:
                config = dict(CONFIG)
            config["launch_at_startup"] = autostart_enabled()
            self._json(config)
            return
        if parsed.path == "/api/update":
            params = parse_qs(parsed.query)
            force = params.get("force", ["0"])[0].lower() in {"1", "true", "yes"}
            self._json(check_for_update(force=force))
            return
        if parsed.path == "/api/spellbook/files":
            self._json(spellbook_discovery_payload())
            return
        if parsed.path == "/api/spellbook":
            params = parse_qs(parsed.query)
            try:
                payload = spellbook_comparison(
                    path_text=params.get("path", [""])[0],
                    character=params.get("character", [""])[0],
                    class_name=params.get("class", [""])[0],
                    level=params.get("level", ["0"])[0],
                )
            except (TypeError, ValueError) as exc:
                self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return
            self._json(payload)
            return
        if parsed.path == "/api/inventory":
            self._json(inventory_payload())
            return
        if parsed.path == "/api/scout-timer":
            params = parse_qs(parsed.query)
            force = params.get("refresh", ["0"])[0].lower() in {"1", "true", "yes"}
            self._json(scout_timer_payload(force=force))
            return
        if parsed.path == "/api/ring8-timer":
            self._json(ring8_timer_payload())
            return
        if parsed.path == "/api/logs":
            params = parse_qs(parsed.query)
            log_dir = params.get("dir", [CONFIG.get("log_dir", "")])[0]
            self._json(list_logs(log_dir))
            return
        if parsed.path == "/api/gina-packages":
            self._json(discover_gina_packages())
            return
        if parsed.path == "/api/state":
            state = dict(STATE)
            state["nparse"] = {
                "zone": current_nparse_zone_name(),
                "zone_key": current_nparse_zone_key(),
                "zone_timer": current_nparse_zone_timer(),
                "entered_at": STATE.get("zone_entered_at", 0),
                "location_x": STATE.get("location_x"),
                "location_y": STATE.get("location_y"),
                "location_z": STATE.get("location_z"),
                "location_raw_x": STATE.get("location_raw_x"),
                "location_raw_y": STATE.get("location_raw_y"),
                "location_raw_z": STATE.get("location_raw_z"),
                "last_location_at": STATE.get("last_location_at", 0),
                "heading": STATE.get("heading", ""),
                "movement_angle": STATE.get("movement_angle"),
                "movement_distance": STATE.get("movement_distance", 0.0),
            }
            state["dps"] = dps_payload()
            state["aggro"] = aggro_payload()
            self._json(state)
            return
        if parsed.path == "/api/aggro":
            self._json(aggro_payload())
            return
        if parsed.path == "/api/dps":
            params = parse_qs(parsed.query)
            limit = int(params.get("limit", ["20"])[0] or 20)
            encounter_id = params.get("encounter", [None])[0]
            filter_preset = params.get("filter", [None])[0]
            custom_start_ts = params.get("start", [None])[0]
            custom_end_ts = params.get("end", [None])[0]
            self._json(dps_payload(
                limit=limit,
                encounter_id=encounter_id,
                filter_preset=filter_preset,
                custom_start_ts=custom_start_ts,
                custom_end_ts=custom_end_ts,
            ))
            return
        if parsed.path == "/api/nparse":
            params = parse_qs(parsed.query)
            zone = params.get("zone", [current_nparse_zone_name()])[0]
            self._json(nparse_payload(zone))
            return
        if parsed.path == "/api/toggle-voice":
            controller = OVERLAY_CONTROLLER
            if controller is None:
                self._json({"error": "overlay controller is not ready"}, HTTPStatus.SERVICE_UNAVAILABLE)
                return
            controller.toggle_config_flag("speak", "Voice")
            with CONFIG_LOCK:
                self._json(CONFIG)
            return
        if parsed.path == "/api/toggle-beep":
            controller = OVERLAY_CONTROLLER
            if controller is None:
                self._json({"error": "overlay controller is not ready"}, HTTPStatus.SERVICE_UNAVAILABLE)
                return
            controller.toggle_config_flag("beep", "Beep")
            with CONFIG_LOCK:
                self._json(CONFIG)
            return
        if parsed.path == "/events":
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            while STATE["running"]:
                try:
                    event = EVENTS.get(timeout=20)
                except queue.Empty:
                    event = {"kind": "ping", "payload": {}, "time": time.time()}
                try:
                    self.wfile.write(f"data: {json.dumps(event)}\n\n".encode("utf-8"))
                    self.wfile.flush()
                except OSError:
                    break
            return
        self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/ring8-timer":
            body = self._body()
            if body.get("clear"):
                stored = dict(DEFAULT_CONFIG["ring8_timer"])
            else:
                entered = str(body.get("time") or "").strip()
                try:
                    roll_time = parse_ring8_time(entered)
                except ValueError as exc:
                    self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
                    return
                stored = {
                    "input": entered,
                    "timestamp": roll_time.timestamp(),
                    "timezone": EASTERN_TIMEZONE_NAME,
                }
            with CONFIG_LOCK:
                CONFIG["ring8_timer"] = stored
                save_config(CONFIG)
            payload = ring8_timer_payload()
            self._json(payload)
            broadcast("status", {"message": "Ring 8 timer updated"})
            return
        if parsed.path == "/api/config":
            incoming = self._body()
            required_sections = {"log_dir", "nparse", "triggers"}
            if (not isinstance(incoming, dict)
                    or not required_sections.issubset(incoming)
                    or not isinstance(incoming.get("nparse"), dict)
                    or not isinstance(incoming.get("triggers"), list)):
                self._json(
                    {"error": "refusing incomplete config payload"},
                    HTTPStatus.BAD_REQUEST,
                )
                return
            try:
                incoming["launch_at_startup"] = set_autostart(
                    bool(incoming.get("launch_at_startup", autostart_enabled()))
                )
            except OSError as exc:
                self._json(
                    {"error": f"Could not update startup setting: {exc}"},
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                )
                return
            with CONFIG_LOCK:
                incoming.setdefault("nparse", {})
                # Ring 8 has its own endpoint and may have been changed by a
                # different open web tab. General settings saves must not
                # overwrite that timer with a stale page-level config copy.
                incoming["ring8_timer"] = dict(
                    CONFIG.get("ring8_timer") or DEFAULT_CONFIG["ring8_timer"]
                )
                current_aggro = dict(DEFAULT_CONFIG["nparse"]["aggro"])
                current_aggro.update(CONFIG.get("nparse", {}).get("aggro") or {})
                incoming_aggro = dict(incoming["nparse"].get("aggro") or {})
                # Geometry is written directly by the live GTK window.  A web
                # settings tab may hold an older copy, so never let its general
                # config save overwrite the current drag/resize result.
                incoming_aggro["geometry"] = list(current_aggro["geometry"])
                current_aggro.update(incoming_aggro)
                incoming["nparse"]["aggro"] = current_aggro
                current_rolls = dict(DEFAULT_CONFIG["nparse"]["rolls"])
                current_rolls.update(CONFIG.get("nparse", {}).get("rolls") or {})
                incoming_rolls = dict(incoming["nparse"].get("rolls") or {})
                incoming_rolls["geometry"] = list(current_rolls["geometry"])
                current_rolls.update(incoming_rolls)
                incoming["nparse"]["rolls"] = current_rolls
                current_frog = dict(DEFAULT_CONFIG["nparse"]["frog_dancer"])
                current_frog.update(CONFIG.get("nparse", {}).get("frog_dancer") or {})
                incoming_frog = dict(incoming["nparse"].get("frog_dancer") or {})
                incoming_frog["geometry"] = list(current_frog["geometry"])
                current_frog.update(incoming_frog)
                incoming["nparse"]["frog_dancer"] = current_frog
                current_dps = dict(
                    CONFIG.get("nparse", {}).get("dps", DEFAULT_CONFIG["nparse"]["dps"])
                )
                if bool(current_dps.get("lock_geometry", DEFAULT_CONFIG["nparse"]["dps"].get("lock_geometry", False))):
                    incoming_dps = dict(incoming["nparse"].get("dps", current_dps))
                    incoming_dps["geometry"] = list(current_dps.get("geometry") or DEFAULT_CONFIG["nparse"]["dps"]["geometry"])
                    incoming_dps["lock_geometry"] = True
                    # A decorated, pointer-active border still invites an X11
                    # edge-resize gesture.  On a fixed-size window XFCE turns
                    # that gesture into apparent jumping, so locked means fully
                    # frameless and non-interactive as well.
                    incoming_dps["frameless"] = True
                    incoming_dps["clickthrough"] = True
                    incoming["nparse"]["dps"] = incoming_dps
                CONFIG.clear()
                CONFIG.update(incoming)
                save_config(CONFIG)
            selected_zone = str(incoming.get("nparse", {}).get("maps", {}).get("selected_zone", "") or "").strip()
            if selected_zone and selected_zone != STATE.get("zone", ""):
                update_zone_state(selected_zone, persist=False)
            zone_key = STATE.get("zone_key", "")
            self._json(CONFIG)
            broadcast("status", {
                "message": "Config saved",
                "active_log": CONFIG.get("active_log", ""),
                "character": STATE.get("character", ""),
                "zone": STATE.get("zone", ""),
                "zone_key": zone_key,
            })
            return
        if parsed.path == "/api/test":
            hit = self._body()
            hit.setdefault("id", str(uuid.uuid4()))
            hit.setdefault("name", "Test")
            hit.setdefault("line", "Manual test alert")
            broadcast("trigger", hit)
            self._json({"ok": True})
            return
        if parsed.path == "/api/test-ch":
            body = self._body()
            line = str(body.get("line") or "Hanbox shouts, 'GG 001 CH -- Beefwich'").strip()
            hit = parse_ch_chain_line(line)
            if not hit:
                self._json({"error": "line did not match CH chain format"}, HTTPStatus.BAD_REQUEST)
                return
            broadcast("ch_chain", hit)
            self._json({"ok": True, "chain": hit})
            return
        if parsed.path == "/api/speak":
            body = self._body()
            text = str(body.get("text", "")).strip()
            if text:
                speak_text(text)
            self._json({"ok": True})
            return
        if parsed.path == "/api/beep":
            beep_audio()
            self._json({"ok": True})
            return
        if parsed.path == "/api/nparse/start":
            body = self._body()
            name = str(body.get("name", "Timer") or "Timer").strip() or "Timer"
            message = str(body.get("message", name) or name).strip() or name
            timer_seconds = int(body.get("timer_seconds") or 0)
            color = str(body.get("color", "#60a5fa") or "#60a5fa")
            hit = {
                "id": str(uuid.uuid4()),
                "trigger_id": "nparse-manual",
                "name": name,
                "message": message,
                "timer_name": name,
                "line": message,
                "raw_line": "",
                "timer_seconds": timer_seconds,
                "color": color,
            }
            if timer_seconds > 0:
                play_trigger_audio(hit)
            broadcast("trigger", hit)
            self._json({"ok": True, "trigger": hit})
            return
        if parsed.path == "/api/overlay/clear-timer":
            body = self._body()
            timer_id = str(body.get("id", "") or "").strip()
            trigger_id = str(body.get("trigger_id", "") or "").strip()
            controller = OVERLAY_CONTROLLER
            if controller is None:
                self._json({"error": "overlay controller is not ready"}, HTTPStatus.SERVICE_UNAVAILABLE)
                return
            if not timer_id and not trigger_id:
                self._json({"error": "missing timer id"}, HTTPStatus.BAD_REQUEST)
                return
            cleared = controller.clear_overlay_timer(timer_id, trigger_id)
            self._json({"ok": True, "cleared": cleared})
            return
        if parsed.path == "/api/overlay/clear-timers":
            controller = OVERLAY_CONTROLLER
            if controller is None:
                self._json({"error": "overlay controller is not ready"}, HTTPStatus.SERVICE_UNAVAILABLE)
                return
            controller.clear_overlay_timers()
            self._json({"ok": True})
            return
        if parsed.path == "/api/overlay/clear-rolls":
            controller = OVERLAY_CONTROLLER
            if controller is None:
                self._json({"error": "overlay controller is not ready"}, HTTPStatus.SERVICE_UNAVAILABLE)
                return
            controller.clear_rolls()
            self._json({"ok": True})
            return
        if parsed.path == "/api/dps/reset":
            with DPS_LOCK:
                remember_dps_encounter_unlocked()
                reset_dps_state()
                payload = dps_payload_unlocked()
            broadcast("dps", payload)
            self._json({"ok": True, "dps": payload})
            return
        if parsed.path == "/api/dps/select":
            body = self._body()
            payload = select_dps_encounter(body.get("direction", "latest"), body.get("encounter_id", ""))
            broadcast("dps", payload)
            self._json({"ok": True, "dps": payload})
            return
        if parsed.path == "/api/import-gina":
            body = self._body()
            try:
                result = import_gina_package(body.get("path", ""))
            except Exception as exc:
                self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return
            self._json(result)
            return
        self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def request_shutdown():
    STATE["running"] = False
    server = globals().get("HTTP_SERVER")
    if server is not None:
        threading.Thread(target=server.shutdown, daemon=True).start()


def main():
    global HTTP_SERVER
    port = int(os.environ.get("LINUX_GINA_PORT") or DEFAULT_PORT)
    thread = threading.Thread(target=monitor_logs, daemon=True)
    thread.start()
    overlay_thread = threading.Thread(target=overlay_loop, daemon=True)
    overlay_thread.start()
    try:
        server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    except OSError:
        url = f"http://127.0.0.1:{port}/?reuse=1"
        print(f"EQ Watcher already appears to be running at {url}", flush=True)
        if os.environ.get("LINUX_GINA_NO_BROWSER") != "1":
            webbrowser.open_new_tab(url)
        STATE["running"] = False
        return
    HTTP_SERVER = server
    url = f"http://127.0.0.1:{port}/"
    STATE["ui_url"] = url
    print(f"EQ Watcher running at {url}", flush=True)
    if os.environ.get("LINUX_GINA_NO_BROWSER") != "1":
        threading.Timer(0.5, lambda: webbrowser.open(f"{url}?reuse=1")).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        STATE["running"] = False
        server.server_close()


if __name__ == "__main__":
    main()
