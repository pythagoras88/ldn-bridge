"""Hosting from the adapter: settings copied from a `scan` capture, so the Switch's game accepts the session."""
from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)


@dataclass
class HostSettings:
    local_communication_id: int
    scene_id: int
    app_version: int
    version: int
    protocol: int
    security_mode: int
    channel: int
    max_participants: int
    application_data: bytes


@dataclass(frozen=True)
class EmulatorSession:
    advertise_data: bytes
    name: bytes
    scene_id: int
    app_version: int
    session_id: bytes
    max_participants: int = 8


class HostTracker:
    """Follows the emulator's session from Scan replies. A missed reply or two doesn't mean it stopped hosting."""

    def __init__(self, misses_allowed: int = 3):
        self.session: EmulatorSession | None = None
        self.misses_allowed = misses_allowed
        self.misses = 0

    def update(self, info) -> bool:
        """Take a Scan result (an mitm NetworkInfo, or None for no reply). Returns True if self.session changed."""
        if info is None:
            self.misses += 1
            if self.session is None or self.misses <= self.misses_allowed:
                return False
            self.session = None
            return True
        self.misses = 0
        host = info.nodes[0]
        session = EmulatorSession(info.advertise_data, host.user_name, info.scene_id, host.local_communication_version,
                                  info.session_id, info.node_count_max)
        changed = session != self.session
        self.session = session
        return changed


def is_station_broadcast(frame: bytes) -> bool:
    """A data frame a station sends straight to every node: neither ToDS nor FromDS (LDN stations talk directly), and
    addressed to ff:ff:ff:ff:ff:ff. The game's traffic is mostly these."""
    if len(frame) < 10:
        return False
    is_data = (frame[0] >> 2) & 3 == 2
    return is_data and frame[1] & 3 == 0 and frame[4:10] == b"\xff" * 6


class BroadcastWatch:
    """Counts the stations' broadcast frames that can and can't be read while hosting, and calls alarm() once if most
    can't. A key left in the MT7612U from an earlier session makes its chip decrypt them with the wrong key, and the
    Switch then waits on "searching" (docs/MILESTONES.md, M6). A few unreadable frames are normal radio damage."""

    def __init__(self, alarm: Callable[[], None], min_unreadable: int = 50, ratio: int = 4):
        self.alarm = alarm
        self.min_unreadable = min_unreadable
        self.ratio = ratio
        self.readable = 0
        self.unreadable = 0
        self.raised = False

    def record(self, readable: bool) -> None:
        if readable:
            self.readable += 1
            return
        self.unreadable += 1
        if (not self.raised and self.unreadable >= self.min_unreadable
                and self.unreadable >= self.ratio * self.readable):
            self.raised = True
            self.alarm()


# What Switch consoles put in their sessions (from scan captures).
NETWORK_VERSION = 4
SECURITY_MODE = 1
HOST_CHANNEL = 6


def settings_for_game(local_communication_id: int, protocol: int = 1) -> HostSettings:
    """Settings to host with when there's no scan capture. The scene, player limit, app version and session data come
    from the emulator each time its game hosts (bridge.publish)."""
    return HostSettings(local_communication_id=local_communication_id, scene_id=0, app_version=0,
                        version=NETWORK_VERSION, protocol=protocol, security_mode=SECURITY_MODE, channel=HOST_CHANNEL,
                        max_participants=8, application_data=b"")


def settings_from_capture(session: dict) -> HostSettings:
    try:
        return HostSettings(
            local_communication_id=int(session["local_communication_id"], 16),
            scene_id=session["scene_id"],
            app_version=session["app_version"],
            version=session["version"],
            protocol=session["protocol"],
            security_mode=session["security_mode"],
            channel=session["channel"],
            max_participants=int(session["participants"].split("/")[1]),
            application_data=bytes.fromhex(session["application_data_hex"]),
        )
    except KeyError as e:
        raise SystemExit(f"This capture has no {e.args[0]}. Run `python -m ldn_bridge scan` again.") from None


def pick_session(sessions: list[dict], scene_id: int | None = None, index: int | None = None) -> dict:
    matches = [s for s in sessions if scene_id is None or s["scene_id"] == scene_id]
    if not matches:
        scenes = sorted({s["scene_id"] for s in sessions})
        raise SystemExit(f"No session with scene {scene_id} in this capture. Its scenes are {scenes}.")
    if index is None and len(matches) > 1:
        scenes = [s["scene_id"] for s in matches]
        raise SystemExit(f"This capture has {len(matches)} sessions, with scenes {scenes}. Choose one with --index.")
    index = index or 0
    if index >= len(matches):
        raise SystemExit(f"--index {index} is too high: {len(matches)} session(s) to choose from.")
    return matches[index]


def run_session(run: Callable[[], None]) -> None:
    """Run the hosting session. The library's nurseries wrap Ctrl-C and failures in exception groups."""
    try:
        run()
    except* KeyboardInterrupt:
        print("Stopped.")
    except* Exception:
        log.exception("Hosting failed")
        raise SystemExit("Hosting failed. If the error is about creating an interface or setting a monitor flag, "
                         "this adapter may not be able to host.") from None


def latest_capture(directory: Path) -> Path:
    captures = sorted(directory.glob("scan-*.json"))
    if not captures:
        raise SystemExit("No scan capture found. While a Switch hosts, run `python -m ldn_bridge scan` first.")
    return captures[-1]


def load_sessions(path: Path) -> list[dict]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SystemExit(f"Capture not found: {path}") from None
