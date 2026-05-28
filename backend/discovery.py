"""
Passive network discovery via mDNS, SSDP, NetBIOS and Ubiquiti Discovery.
All methods return dicts used to enrich device hostnames and icons.
"""

import asyncio
import ipaddress
import re
import socket
import struct
import time
import urllib.request
import xml.etree.ElementTree as ET
from typing import Optional


# ── SSDP / UPnP ──────────────────────────────────────────────────────────────

_SSDP_ADDR = "239.255.255.250"
_SSDP_PORT = 1900
_SSDP_MSG = (
    "M-SEARCH * HTTP/1.1\r\n"
    f"HOST: {_SSDP_ADDR}:{_SSDP_PORT}\r\n"
    'MAN: "ssdp:discover"\r\n'
    "MX: 3\r\n"
    "ST: ssdp:all\r\n"
    "\r\n"
).encode()


def _ssdp_sync(timeout: float) -> dict[str, str]:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 4)
    sock.settimeout(0.5)
    try:
        sock.sendto(_SSDP_MSG, (_SSDP_ADDR, _SSDP_PORT))
        locations: dict[str, str] = {}
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                data, addr = sock.recvfrom(65507)
                ip = addr[0]
                if ip in locations:
                    continue
                text = data.decode("utf-8", errors="ignore")
                m = re.search(r"LOCATION:\s*(\S+)", text, re.IGNORECASE)
                if m:
                    locations[ip] = m.group(1).strip()
            except socket.timeout:
                continue
            except Exception:
                continue
    finally:
        sock.close()

    names: dict[str, str] = {}
    for ip, location in locations.items():
        try:
            req = urllib.request.Request(location, headers={"User-Agent": "DudeModern"})
            with urllib.request.urlopen(req, timeout=2) as resp:
                root = ET.fromstring(resp.read())
            el = root.find(".//{urn:schemas-upnp-org:device-1-0}friendlyName")
            if el is not None and el.text and el.text.strip():
                names[ip] = el.text.strip()
        except Exception:
            pass
    return names


async def discover_ssdp(timeout: float = 4.0) -> dict[str, str]:
    """UPnP SSDP M-SEARCH → {ip: friendly_name}"""
    return await asyncio.to_thread(_ssdp_sync, timeout)


# ── mDNS / Bonjour ────────────────────────────────────────────────────────────

# Service types to browse — ordered by name quality (best last, wins the dict)
_MDNS_SERVICES = [
    "_http._tcp.local.",
    "_smb._tcp.local.",
    "_printer._tcp.local.",
    "_ipp._tcp.local.",
    "_workstation._tcp.local.",
    "_homekit._tcp.local.",
    "_airplay._tcp.local.",
    "_googlecast._tcp.local.",
    "_device-info._tcp.local.",
]

# mDNS service type → icon hint (used to auto-set icon on new devices)
MDNS_ICON_HINTS: dict[str, str] = {
    "_googlecast._tcp.local.": "speaker",
    "_airplay._tcp.local.":    "speaker",
    "_homekit._tcp.local.":    "iot",
    "_printer._tcp.local.":    "printer",
    "_ipp._tcp.local.":        "printer",
    "_smb._tcp.local.":        "pc",
    "_workstation._tcp.local.": "pc",
}


def _mdns_sync(timeout: float) -> tuple[dict[str, str], dict[str, str]]:
    """Returns (ip→name, ip→icon_hint)"""
    try:
        from zeroconf import Zeroconf, ServiceBrowser, ServiceStateChange
    except ImportError:
        return {}, {}

    names: dict[str, str] = {}
    icons: dict[str, str] = {}

    def on_change(zeroconf, service_type, name, state_change):
        if state_change is not ServiceStateChange.Added:
            return
        try:
            info = zeroconf.get_service_info(service_type, name, timeout=800)
            if not info or not info.addresses:
                return
            ip = socket.inet_ntoa(info.addresses[0])
            # Strip service suffix to get a clean device name
            suffix = "." + service_type.rstrip(".")
            device_name = name[: -len(suffix)] if name.endswith(suffix) else name
            device_name = device_name.strip()
            if device_name:
                names[ip] = device_name
            hint = MDNS_ICON_HINTS.get(service_type)
            if hint and ip not in icons:
                icons[ip] = hint
        except Exception:
            pass

    zc = Zeroconf()
    try:
        browsers = [ServiceBrowser(zc, stype, handlers=[on_change]) for stype in _MDNS_SERVICES]  # noqa
        time.sleep(timeout)
    finally:
        zc.close()

    return names, icons


async def discover_mdns(timeout: float = 6.0) -> tuple[dict[str, str], dict[str, str]]:
    """mDNS/Bonjour → ({ip: name}, {ip: icon_hint})"""
    return await asyncio.to_thread(_mdns_sync, timeout)


# ── NetBIOS ───────────────────────────────────────────────────────────────────

# NetBIOS Name Status Request (wildcard query)
_NBSTAT = bytes([
    0xA4, 0x5E, 0x00, 0x00, 0x00, 0x01,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x20,
    *b"CKAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
    0x00, 0x00, 0x21, 0x00, 0x01,
])


def _netbios_query(ip: str, timeout: float) -> Optional[str]:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(timeout)
        sock.sendto(_NBSTAT, (ip, 137))
        data, _ = sock.recvfrom(1024)
        sock.close()
        if len(data) < 57:
            return None
        num_names = data[56]
        offset = 57
        for _ in range(num_names):
            if offset + 18 > len(data):
                break
            name = data[offset:offset + 15].decode("ascii", errors="ignore").rstrip()
            name_type = data[offset + 15]
            flags = int.from_bytes(data[offset + 16:offset + 18], "big")
            offset += 18
            # type 0x00 = workstation unique name (not a group)
            if name_type == 0x00 and not (flags & 0x8000):
                clean = name.strip()
                if clean:
                    return clean
        return None
    except Exception:
        return None


async def discover_netbios(ips: list[str], timeout: float = 0.8) -> dict[str, str]:
    """NetBIOS Name Status → {ip: computer_name} (Windows / Samba hosts)"""
    results = await asyncio.gather(
        *[asyncio.to_thread(_netbios_query, ip, timeout) for ip in ips],
        return_exceptions=True,
    )
    return {
        ip: name
        for ip, name in zip(ips, results)
        if isinstance(name, str) and name
    }


# ── Ubiquiti Discovery Protocol ───────────────────────────────────────────────

_UBIQUITI_PORT    = 10001
_UBIQUITI_PROBE_V1 = bytes([0x01, 0x00, 0x00, 0x00])   # AirOS v1
_UBIQUITI_PROBE_V2 = bytes([0x02, 0x0a, 0x00, 0x00])   # UniFi v2
_UBIQUITI_PROBE    = _UBIQUITI_PROBE_V1                 # default


def _ubiquiti_icon(model: str) -> str:
    m = model.upper()
    if any(x in m for x in ("USW", "SWITCH")):
        return "switch"
    if any(x in m for x in (
        "UAP", "U2-", "U5-", "U6-", "U7-", "UNIFI-AP",
        "NANOSTATION", "NANOB", "BULLET", "POWERBEAM",
        "LITEBEAM", "AIRFIBER", "CPE",
    )):
        return "ap"
    # EdgeRouter, UDM, USG, etc.
    return "router"


def _parse_ubiquiti_response(data: bytes) -> dict:
    """Parse Ubiquiti TLV response payload (skip 4-byte header)."""
    result: dict = {}
    offset = 4          # skip header
    n = len(data)
    while offset + 3 <= n:
        tlv_type = data[offset]
        tlv_len  = struct.unpack_from(">H", data, offset + 1)[0]
        offset  += 3
        if offset + tlv_len > n:
            break
        value   = data[offset: offset + tlv_len]
        offset += tlv_len

        if tlv_type == 0x01 and tlv_len == 6:
            result["mac"] = ":".join(f"{b:02X}" for b in value)
        elif tlv_type == 0x02 and tlv_len == 10:
            # 6-byte MAC + 4-byte IP
            result.setdefault("ip", socket.inet_ntoa(value[6:10]))
        elif tlv_type == 0x03:
            result["firmware"] = value.decode("utf-8", errors="ignore").strip()
        elif tlv_type == 0x0A and tlv_len == 4:
            result["uptime"] = struct.unpack_from(">I", value)[0]
        elif tlv_type == 0x0B:
            result["hostname"] = value.decode("utf-8", errors="ignore").strip()
        elif tlv_type == 0x0C:
            result["model"] = value.decode("utf-8", errors="ignore").strip()

    return result


def _make_ubiquiti_socket() -> socket.socket:
    """
    Create a UDP socket for Ubiquiti discovery.
    Many Ubiquiti devices only respond when the probe arrives FROM port 10001,
    so we try to bind to that port first and fall back to any free port.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.settimeout(0.5)
    try:
        sock.bind(("", _UBIQUITI_PORT))   # preferred: source port = 10001
    except OSError:
        sock.bind(("", 0))                # fallback: any free port
    return sock


def _ubiquiti_sync(
    broadcast_addrs: list[str],
    unicast_ips: list[str],
    timeout: float,
) -> dict[str, dict]:
    """
    Send Ubiquiti discovery probes (v1 + v2) and collect responses.
    - broadcast_addrs: subnet broadcast IPs (same L2 segment only)
    - unicast_ips: individual device IPs (crosses routed subnets)
    """
    sock = _make_ubiquiti_socket()
    probes = [_UBIQUITI_PROBE_V1, _UBIQUITI_PROBE_V2]
    targets = [(a, _UBIQUITI_PORT) for a in broadcast_addrs] + \
              [(ip, _UBIQUITI_PORT) for ip in unicast_ips]
    try:
        for probe in probes:
            for target in targets:
                try:
                    sock.sendto(probe, target)
                except Exception:
                    pass

        probed_ips = set(broadcast_addrs) | set(unicast_ips)

        results: dict[str, dict] = {}
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                data, addr = sock.recvfrom(65507)
                src_ip = addr[0]
                # Accept broadcast replies (src not in probed_ips) only if
                # the packet is a real response (>4 bytes with TLV payload)
                if src_ip not in probed_ips and len(data) <= 4:
                    continue   # discard spurious probes from other devices
                if len(data) < 4 or data[0] not in (0x01, 0x02):
                    continue
                parsed = _parse_ubiquiti_response(data)
                if not parsed:
                    continue
                if "model" in parsed:
                    parsed["icon"] = _ubiquiti_icon(parsed["model"])
                ip = parsed.get("ip") or src_ip
                results[ip] = parsed
                if src_ip != ip:
                    results[src_ip] = parsed
            except socket.timeout:
                continue
            except Exception:
                continue
    finally:
        sock.close()
    return results


def ubiquiti_probe_raw(ip: str, timeout: float = 3.0) -> dict:
    """
    Send both probe versions to a single IP and return raw debug info.
    Only counts responses that actually come FROM the target IP.
    Used by the /api/debug/ubiquiti endpoint.
    """
    sock = _make_ubiquiti_socket()
    side_packets = []
    try:
        for probe in [_UBIQUITI_PROBE_V1, _UBIQUITI_PROBE_V2]:
            sock.sendto(probe, (ip, _UBIQUITI_PORT))

        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                data, addr = sock.recvfrom(65507)
                src_ip = addr[0]
                if src_ip != ip:
                    # Log side-traffic for diagnostics but don't treat as answer
                    side_packets.append({
                        "src_ip":  src_ip,
                        "raw_hex": data.hex(),
                        "raw_len": len(data),
                    })
                    continue
                parsed = _parse_ubiquiti_response(data)
                if "model" in parsed:
                    parsed["icon"] = _ubiquiti_icon(parsed["model"])
                return {
                    "raw_hex":     data.hex(),
                    "raw_len":     len(data),
                    "header":      data[:4].hex(),
                    "src_ip":      src_ip,
                    "parsed":      parsed,
                    "side_packets": side_packets,
                }
            except socket.timeout:
                continue
    finally:
        sock.close()
    return {
        "raw_hex":      None,
        "parsed":       None,
        "error":        "no response from target",
        "side_packets": side_packets,
    }


async def discover_ubiquiti(
    networks: list[str] | None = None,
    unicast_ips: list[str] | None = None,
    timeout: float = 3.0,
) -> dict[str, dict]:
    """
    Ubiquiti Discovery Protocol (UDP 10001).

    Two complementary strategies:
    - Broadcast to each subnet's broadcast address (same L2 only)
    - Unicast to every known device IP (works across routed subnets)

    Returns {ip: {hostname?, model?, firmware?, mac?, uptime?, icon?}}.
    """
    broadcast_addrs = ["255.255.255.255"]
    for net in (networks or []):
        try:
            bcast = str(ipaddress.ip_network(net, strict=False).broadcast_address)
            if bcast not in broadcast_addrs:
                broadcast_addrs.append(bcast)
        except Exception:
            pass

    return await asyncio.to_thread(
        _ubiquiti_sync, broadcast_addrs, unicast_ips or [], timeout
    )
