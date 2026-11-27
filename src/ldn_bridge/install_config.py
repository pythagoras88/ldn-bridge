"""Used by install.sh: fill in config.toml and the emulator's settings. Never prints the passphrase or key values.

    python -m ldn_bridge.install_config --mac <adapter MAC> [--emulator <AppImage>] [--keys <prod.keys>]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore

from .config import PROJECT_ROOT, REQUIRED_KEYS

DEFAULT_EMULATOR = "~/Applications/ryujinx-1.3.3-x64.AppImage"
DEFAULT_KEYS = "~/.config/Ryujinx/system/prod.keys"
RYUJINX_CONFIG = "~/.config/Ryujinx/Config.json"
LDN_MITM = 2  # Ryujinx's MultiplayerMode: Disabled, LdnRyu, LdnMitm

_SECTION = re.compile(r"^\s*\[([^\]]+)\]\s*$")


def set_value(text: str, section: str, key: str, literal: str) -> str:
    """Set `key = literal` in [section], keeping every other line and comment. Adds the key or section if missing."""
    lines = text.splitlines(keepends=True)
    if lines and not lines[-1].endswith("\n"):
        lines[-1] += "\n"
    key_line = re.compile(rf"^\s*{re.escape(key)}\s*=")
    current = None
    header = None
    for i, line in enumerate(lines):
        m = _SECTION.match(line)
        if m:
            current = m.group(1).strip()
            if current == section:
                header = i
            continue
        if current == section and key_line.match(line):
            lines[i] = f"{key} = {literal}\n"
            return "".join(lines)
    if header is None:
        if lines and lines[-1].strip():
            lines.append("\n")
        lines += [f"[{section}]\n", f"{key} = {literal}\n"]
    else:
        lines.insert(header + 1, f"{key} = {literal}\n")
    return "".join(lines)


def toml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def protocols_for(key_names) -> list[int]:
    names = set(key_names)
    return [p for p, needed in REQUIRED_KEYS.items() if all(k in names for k in needed)]


def update_ryujinx(config: dict, ifname: str) -> list[str]:
    """Settings the bridge needs. Returns what changed."""
    wanted = {
        "multiplayer_mode": (LDN_MITM, "Multiplayer mode: ldn_mitm"),
        "multiplayer_lan_interface_id": (ifname, f"Network interface: {ifname}"),
        "enable_internet_access": (False, "Guest Internet Access: off"),
    }
    changed = []
    for key, (value, label) in wanted.items():
        if config.get(key) != value:
            config[key] = value
            changed.append(label)
    return changed


def _key_names(path: str) -> list[str]:
    import ldn  # only on Linux, inside the venv

    return list(ldn.load_keys(path))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mac", required=True)
    ap.add_argument("--emulator", default="")
    ap.add_argument("--keys", default="")
    args = ap.parse_args(argv)

    path = PROJECT_ROOT / "config.toml"
    if not path.exists():
        shutil.copyfile(PROJECT_ROOT / "config.example.toml", path)
        print("Created config.toml.")
    else:
        print("Keeping your config.toml, and updating the adapter, emulator and keys in it.")
    os.chmod(path, 0o600)
    text = path.read_text(encoding="utf-8")
    data = tomllib.loads(text)
    ldn_section = data.get("ldn", {})
    launch = data.get("launch", {})

    text = set_value(text, "ldn", "adapter_mac", toml_string(args.mac.lower()))

    keys_path = ldn_section.get("keys_path") or DEFAULT_KEYS
    if not os.path.isfile(os.path.expanduser(keys_path)) and args.keys:
        keys_path = args.keys
        text = set_value(text, "ldn", "keys_path", toml_string(keys_path))
    warnings = []
    if os.path.isfile(os.path.expanduser(keys_path)):
        protocols = protocols_for(_key_names(os.path.expanduser(keys_path)))
        if protocols:
            text = set_value(text, "ldn", "protocols", json.dumps(protocols))
            print(f"Keys: {keys_path} (protocols {protocols}).")
        else:
            warnings.append(f"{keys_path} is missing the keys the bridge needs. Install newer firmware keys in Ryujinx.")
    else:
        warnings.append("No prod.keys found. Set up Ryujinx with your own keys, then run the installer again.")

    emulator = launch.get("emulator", "")
    if args.emulator and not os.path.isfile(os.path.expanduser(emulator or DEFAULT_EMULATOR)):
        text = set_value(text, "launch", "emulator", toml_string(args.emulator))
        emulator = args.emulator
    print(f"Emulator: {emulator or DEFAULT_EMULATOR}")
    game = launch.get("game", "")
    if game and not os.path.isfile(os.path.expanduser(game)):
        text = set_value(text, "launch", "game", '""')
        warnings.append("The game in [launch] no longer exists, so Play opens the game list. Set game in config.toml "
                        "to open one directly.")

    path.write_text(text, encoding="utf-8")

    if not ldn_section.get("password_hex"):
        warnings.append("No passphrase yet. Put your saved password_hex in config.toml, or capture it again "
                        "(docs/SETUP.md, section 4).")

    ryu = Path(os.path.expanduser(RYUJINX_CONFIG))
    if ryu.exists():
        config = json.loads(ryu.read_text(encoding="utf-8"))
        changed = update_ryujinx(config, ldn_section.get("ifname", "ldn"))
        if changed:
            ryu.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")
            print("Ryujinx settings: " + ", ".join(changed) + ".")
        else:
            print("Ryujinx settings already right.")
    else:
        warnings.append("Ryujinx has no settings yet. Open it once, close it, and run the installer again so it can "
                        "set Multiplayer mode to ldn_mitm.")

    for w in warnings:
        print("NOTE: " + w)
    return 0


if __name__ == "__main__":
    sys.exit(main())
