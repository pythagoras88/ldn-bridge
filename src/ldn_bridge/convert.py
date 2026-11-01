"""Convert the ldn library's over-the-air NetworkInfo into an ldn_mitm NetworkInfo.

Duck-typed on the ldn objects so it can be tested without the library installed.
"""
from __future__ import annotations

from .mitm_proto import MAX_NODES, NetworkInfo, NodeInfo

# The tested game uses the default id, -1, on the emulator, which ldn_mitm mode never resolves. A game that uses its
# real id needs this changed (docs/LDN_MITM_PROTOCOL.md).
EMULATOR_LOCAL_COMMUNICATION_ID = 0xFFFFFFFFFFFFFFFF


def mac_bytes(mac) -> bytes:
    if isinstance(mac, (bytes, bytearray)):
        return bytes(mac)
    if hasattr(mac, "encode"):
        return mac.encode()
    return bytes(mac)


def from_ldn(info, *, host_ip_override: str | None = None) -> NetworkInfo:
    """Build an ldn_mitm NetworkInfo from an ldn.NetworkInfo.

    host_ip_override: replace node 0's IP (used in ScanResp so the emulator's TCP Connect
    lands on the bridge; see docs/DESIGN.md step 5). Leave None for SyncNetwork.
    """
    nodes: list[NodeInfo] = []
    for i, p in enumerate(list(info.participants)[:MAX_NODES]):
        nodes.append(NodeInfo(
            ip=p.ip_address,
            mac=mac_bytes(p.mac_address),
            node_id=i,
            is_connected=bool(p.connected),
            user_name=bytes(p.name)[:32],
            local_communication_version=p.app_version & 0xFFFF,
        ))
    while len(nodes) < MAX_NODES:
        nodes.append(NodeInfo(node_id=len(nodes)))

    if host_ip_override is not None:
        nodes[0].ip = host_ip_override

    ssid = bytes(info.ssid)
    return NetworkInfo(
        local_communication_id=EMULATOR_LOCAL_COMMUNICATION_ID,
        scene_id=info.scene_id & 0xFFFF,
        session_id=ssid[:16],
        bssid=mac_bytes(info.address),
        ssid=ssid.hex().encode(),
        channel=info.channel,
        security_parameter=bytes(info.server_random)[:16],
        security_mode=info.security_mode,
        station_accept_policy=info.accept_policy,
        node_count_max=info.max_participants,
        node_count=sum(1 for n in nodes if n.is_connected),
        nodes=nodes,
        advertise_data=bytes(info.application_data),
    )
