from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass
class Config:
    keys_path: str = "~/.config/Ryujinx/system/prod.keys"
    phyname: str = "phy1"
    adapter_mac: str = ""
    ifname: str = "ldn"
    channels: list[int] = field(default_factory=lambda: [1, 6, 11, 36, 40, 44, 48])
    protocols: list[int] = field(default_factory=lambda: [1])
    password: bytes = b""
    nickname: str = "Deck"
    local_communication_id: int | None = None
    scene_id: int | None = None
    mitm_port: int = 11452

    @property
    def keys_file(self) -> str:
        return os.path.expanduser(self.keys_path)


def _int(v):
    if v is None or v == "" or v == -1:
        return None
    return int(v, 0) if isinstance(v, str) else int(v)


def load(path: str | os.PathLike | None = None) -> Config:
    p = Path(path) if path else PROJECT_ROOT / "config.toml"
    if not p.exists():
        raise SystemExit(f"Missing {p}. Copy config.example.toml to config.toml and edit it.")
    data = tomllib.loads(p.read_text(encoding="utf-8"))
    ldn = data.get("ldn", {})
    game = data.get("game", {})
    mitm = data.get("mitm", {})
    cfg = Config()
    cfg.keys_path = ldn.get("keys_path", cfg.keys_path)
    cfg.phyname = ldn.get("phyname", cfg.phyname)
    cfg.adapter_mac = ldn.get("adapter_mac", cfg.adapter_mac)
    cfg.ifname = ldn.get("ifname", cfg.ifname)
    cfg.channels = list(ldn.get("channels", cfg.channels))
    cfg.protocols = list(ldn.get("protocols", cfg.protocols))
    cfg.password = bytes.fromhex(ldn.get("password_hex", "") or "")
    cfg.nickname = ldn.get("nickname", cfg.nickname)
    cfg.local_communication_id = _int(game.get("local_communication_id"))
    cfg.scene_id = _int(game.get("scene_id"))
    cfg.mitm_port = int(mitm.get("port", cfg.mitm_port))
    return cfg
