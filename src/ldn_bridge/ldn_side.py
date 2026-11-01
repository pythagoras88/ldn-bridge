"""Thin, config-driven wrappers over kinnay's ldn library."""
from __future__ import annotations

import logging

import ldn

from . import adapter
from .captures import save_capture  # noqa: F401  (re-exported for callers)
from .config import Config
from .convert import mac_bytes

log = logging.getLogger(__name__)

REQUIRED_KEYS = {
    1: ["aes_kek_generation_source", "aes_key_generation_source", "master_key_00"],
    3: ["aes_kek_generation_source", "aes_key_generation_source", "master_key_12"],
}
PLATFORMS = {ldn.PLATFORM_NX: "Switch", ldn.PLATFORM_OUNCE: "Switch 2"}


def load_keys(cfg: Config) -> dict[str, bytes]:
    return ldn.load_keys(cfg.keys_file)


def key_report(keys: dict[str, bytes]) -> dict[int, list[str]]:
    """Missing key *names* per protocol. Never returns values."""
    return {proto: [k for k in names if k not in keys] for proto, names in REQUIRED_KEYS.items()}


async def scan(cfg: Config, keys) -> list:
    if cfg.adapter_mac:
        cfg.phyname = adapter.prepare(cfg.adapter_mac)
    log.info("scanning phy=%s channels=%s protocols=%s", cfg.phyname, cfg.channels, cfg.protocols)
    nets = await ldn.scan(keys, ifname=cfg.ifname, phyname=cfg.phyname,
                          channels=cfg.channels, protocols=cfg.protocols)
    return [n for n in nets if matches(cfg, n)]


def matches(cfg: Config, n) -> bool:
    if cfg.local_communication_id is not None and n.local_communication_id != cfg.local_communication_id:
        return False
    if cfg.scene_id is not None and n.scene_id != cfg.scene_id:
        return False
    return True


def network_to_dict(n) -> dict:
    return {
        "protocol": n.protocol,
        "local_communication_id": f"0x{n.local_communication_id:016x}",
        "scene_id": n.scene_id,
        "app_version": n.app_version,
        "version": n.version,
        "security_mode": n.security_mode,
        "band": n.band,
        "channel": n.channel,
        "host_mac": mac_bytes(n.address).hex(":"),
        "ssid": bytes(n.ssid).hex(),
        "accept_policy": n.accept_policy,
        "participants": f"{n.num_participants}/{n.max_participants}",
        "application_data_hex": bytes(n.application_data).hex(),
        "members": [
            {"index": i, "name": p.name.decode(errors="replace"), "ip": p.ip_address,
             "mac": mac_bytes(p.mac_address).hex(":"), "app_version": p.app_version,
             "platform": PLATFORMS.get(p.platform, p.platform)}
            for i, p in enumerate(n.participants) if p.connected
        ],
    }


def connect_param(cfg: Config, keys, network) -> "ldn.ConnectNetworkParam":
    p = ldn.ConnectNetworkParam()
    p.keys = keys
    p.network = network
    p.phyname = cfg.phyname
    p.ifname = cfg.ifname
    p.password = cfg.password
    p.name = cfg.nickname.encode()[:32]
    p.app_version = network.app_version
    p.platform = ldn.PLATFORM_NX
    return p


def create_param(cfg: Config, keys, *, local_communication_id: int, scene_id: int, app_version: int,
                 application_data: bytes, max_participants: int = 8) -> "ldn.CreateNetworkParam":
    p = ldn.CreateNetworkParam()
    p.keys = keys
    p.phyname = cfg.phyname
    p.ifname = cfg.ifname
    p.local_communication_id = local_communication_id
    p.scene_id = scene_id
    p.app_version = app_version
    p.application_data = application_data
    p.max_participants = max_participants
    p.password = cfg.password
    p.name = cfg.nickname.encode()[:32]
    return p
