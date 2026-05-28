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


# ── TCP Banner / HTTP fingerprinting ─────────────────────────────────────────

# SSH banner keywords → (vendor label, icon)
_SSH_HINTS: list[tuple[str, str, str]] = [
    ("UBNT",      "Ubiquiti",       "ap"),
    ("ubnt",      "Ubiquiti",       "ap"),
    ("AirOS",     "Ubiquiti AirOS", "ap"),
    ("UniFi",     "Ubiquiti UniFi", "router"),
    ("RouterOS",  "MikroTik",       "router"),
    ("MikroTik",  "MikroTik",       "router"),
    ("Cisco",     "Cisco",          "router"),
    ("Juniper",   "Juniper",        "router"),
    ("Synology",  "Synology",       "server"),
    ("QNAP",      "QNAP",           "server"),
    ("Hikvision", "Hikvision",      "camera"),
    ("Dahua",     "Dahua",          "camera"),
    ("Axis",      "Axis",           "camera"),
    ("dropbear",  "Embedded/Network", "unknown"),  # generic embedded Linux
]

# HTTP page title / Server header keywords → (vendor label, icon)
_HTTP_HINTS: list[tuple[str, str, str]] = [
    ("AirOS",      "Ubiquiti AirOS", "ap"),
    ("airMAX",     "Ubiquiti AirMAX","ap"),
    ("UniFi",      "Ubiquiti UniFi", "router"),
    ("EdgeOS",     "Ubiquiti EdgeOS","router"),
    ("RouterOS",   "MikroTik",       "router"),
    ("MikroTik",   "MikroTik",       "router"),
    ("Synology",   "Synology",       "server"),
    ("QNAP",       "QNAP",           "server"),
    ("Hikvision",  "Hikvision",      "camera"),
    ("Dahua",      "Dahua",          "camera"),
    ("Proxmox",    "Proxmox",        "server"),
    ("pfSense",    "pfSense",        "router"),
    ("OPNsense",   "OPNsense",       "router"),
    ("OpenWrt",    "OpenWrt",        "router"),
    ("DD-WRT",     "DD-WRT",         "router"),
    ("Home Assistant", "Home Assistant", "server"),
    ("Frigate",    "Frigate",        "server"),
]


def _apply_hints(text: str, hints: list[tuple]) -> tuple[str | None, str | None]:
    """Return (vendor, icon) for the first matching hint keyword."""
    for keyword, vendor, icon in hints:
        if keyword.lower() in text.lower():
            return vendor, icon
    return None, None


async def _grab_ssh_banner(ip: str, timeout: float) -> str | None:
    """Return the SSH version string (first line) or None."""
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(ip, 22), timeout=timeout
        )
        line = await asyncio.wait_for(reader.readline(), timeout=timeout)
        writer.close()
        await writer.wait_closed()
        return line.decode("utf-8", errors="ignore").strip()
    except Exception:
        return None


async def _grab_http_title(ip: str, port: int, timeout: float) -> str | None:
    """Return HTTP page title or Server header, or None."""
    try:
        ssl_ctx = None
        if port in (443, 8443):
            import ssl
            ssl_ctx = ssl.create_default_context()
            ssl_ctx.check_hostname = False
            ssl_ctx.verify_mode = ssl.CERT_NONE

        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(ip, port, ssl=ssl_ctx), timeout=timeout
        )
        writer.write(
            f"GET / HTTP/1.0\r\nHost: {ip}\r\nUser-Agent: DudeModern/1.0\r\n\r\n"
            .encode()
        )
        await writer.drain()

        data = b""
        deadline = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < deadline:
            try:
                chunk = await asyncio.wait_for(reader.read(4096), timeout=0.8)
                if not chunk:
                    break
                data += chunk
                if b"</title>" in data.lower() or len(data) > 8192:
                    break
            except Exception:
                break
        writer.close()

        text = data.decode("utf-8", errors="ignore")
        # Try <title> first
        m = re.search(r"<title[^>]*>(.*?)</title>", text, re.IGNORECASE | re.DOTALL)
        if m:
            return m.group(1).strip()[:120]
        # Fall back to Server header
        m = re.search(r"\nServer:\s*(.+)", text, re.IGNORECASE)
        if m:
            return m.group(1).strip()[:120]
    except Exception:
        pass
    return None


async def fingerprint_device(ip: str, web_port: int | None = None,
                              timeout: float = 2.0) -> dict:
    """
    Grab SSH banner + HTTP title for a single device.
    Returns {ssh_banner, http_title, vendor, icon}.

    HTTP probing order:
    1. web_port if provided (device-specific)
    2. Port 80 (plain HTTP)
    3. Port 443 (HTTPS, fallback — many embedded devices redirect 80→443)
    """
    # Determine which HTTP ports to try, avoiding duplicates
    http_ports: list[int] = []
    if web_port and web_port not in (80, 443):
        http_ports.append(web_port)
    http_ports += [80, 443]

    # Run SSH grab + all HTTP probes in parallel
    ssh_task = _grab_ssh_banner(ip, timeout)
    http_tasks = [_grab_http_title(ip, p, timeout) for p in http_ports]

    all_results = await asyncio.gather(ssh_task, *http_tasks, return_exceptions=True)
    ssh_banner = all_results[0] if not isinstance(all_results[0], Exception) else None
    http_results = [
        r if not isinstance(r, Exception) else None
        for r in all_results[1:]
    ]

    # Pick the first non-None HTTP result
    http_title = next((r for r in http_results if r), None)

    vendor, icon = None, None
    if ssh_banner:
        vendor, icon = _apply_hints(ssh_banner, _SSH_HINTS)
    if http_title and not vendor:
        vendor, icon = _apply_hints(http_title, _HTTP_HINTS)

    return {
        "ssh_banner": ssh_banner,
        "http_title": http_title,
        "vendor":     vendor,
        "icon":       icon,
    }


async def fingerprint_devices(
    ip_port_pairs: list[tuple[str, int | None]],
    timeout: float = 1.5,
) -> dict[str, dict]:
    """
    Fingerprint multiple devices in parallel.
    ip_port_pairs: [(ip, web_port_or_None), ...]
    Returns {ip: {ssh_banner, http_title, vendor, icon}}.
    """
    results = await asyncio.gather(
        *[fingerprint_device(ip, port, timeout) for ip, port in ip_port_pairs],
        return_exceptions=True,
    )
    return {
        ip: r
        for (ip, _), r in zip(ip_port_pairs, results)
        if isinstance(r, dict) and (r.get("vendor") or r.get("ssh_banner") or r.get("http_title"))
    }


# ── Ubiquiti Discovery Protocol ───────────────────────────────────────────────
#
# Protocol reference: https://github.com/digineo/ubnt-tools
# Packet format: version(1) + command(1) + length(2) + TLV payload
# Probe: version=1 or 2, command=0, length=0  →  \xVV\x00\x00\x00
#
# Targets (from ubnt-tools source):
#   - Multicast 233.89.188.1:10001  (Ubiquiti multicast group)
#   - Broadcast 255.255.255.255:10001  (and per-subnet broadcasts)
#   - Unicast to each device IP  (crosses routed subnets)
#
# Source port MUST be 10001 — AirOS devices filter probes by source port.

_UBIQUITI_PORT      = 10001
_UBIQUITI_MULTICAST = "233.89.188.1"          # Ubiquiti discovery multicast group
_UBIQUITI_PROBE_V1  = bytes([0x01, 0x00, 0x00, 0x00])   # AirOS / airMAX
_UBIQUITI_PROBE_V2  = bytes([0x02, 0x00, 0x00, 0x00])   # UniFi OS / EdgeOS


# TLV tag IDs (from ubnt-tools/discovery/tag.go)
_TAG_MAC        = 0x01   # 6-byte MAC
_TAG_IP_INFO    = 0x02   # 6-byte MAC + 4-byte IP
_TAG_FIRMWARE   = 0x03   # string
_TAG_UPTIME     = 0x0A   # uint32 seconds
_TAG_HOSTNAME   = 0x0B   # string
_TAG_PLATFORM   = 0x0C   # string  (platform/model for V1 AirOS)
_TAG_ESSID      = 0x0D   # string  (wireless SSID)
_TAG_WMODE      = 0x0E   # uint8   (2=Station, 3=AccessPoint)
_TAG_WEBUI      = 0x0F   # string  (Web UI URL)
_TAG_MODEL_V1   = 0x14   # string  (model name, V1 protocol)
_TAG_MODEL_V2   = 0x15   # string  (model name, V2 protocol)
_TAG_SSHD_PORT  = 0x1C   # uint32  (SSH daemon port)


def _ubiquiti_icon(model: str) -> str:
    m = model.upper()
    if any(x in m for x in ("USW", "SWITCH")):
        return "switch"
    if any(x in m for x in (
        "UAP", "U2-", "U5-", "U6-", "U7-", "UNIFI-AP",
        "NANOSTATION", "NANOB", "BULLET", "POWERBEAM",
        "LITEBEAM", "AIRFIBER", "CPE", "NANOBEAM",
    )):
        return "ap"
    # EdgeRouter, UDM, USG, ERLite, etc.
    return "router"


def _parse_ubiquiti_response(data: bytes) -> dict:
    """
    Parse Ubiquiti TLV response.
    Header: version(1) + command(1) + length(2) — skip 4 bytes, then read TLVs.
    Each TLV: type(1) + length(2, big-endian) + value(n).
    """
    if len(data) < 4:
        return {}
    result: dict = {}
    offset = 4          # skip 4-byte header
    n = len(data)
    while offset + 3 <= n:
        tlv_type = data[offset]
        tlv_len  = struct.unpack_from(">H", data, offset + 1)[0]
        offset  += 3
        if offset + tlv_len > n:
            break
        value   = data[offset: offset + tlv_len]
        offset += tlv_len

        try:
            if tlv_type == _TAG_MAC and tlv_len == 6:
                result["mac"] = ":".join(f"{b:02X}" for b in value)
            elif tlv_type == _TAG_IP_INFO and tlv_len >= 10:
                # 6-byte MAC + 4-byte IP (may repeat for multiple interfaces)
                result.setdefault("ip", socket.inet_ntoa(value[6:10]))
            elif tlv_type == _TAG_FIRMWARE:
                result["firmware"] = value.decode("utf-8", errors="ignore").strip()
            elif tlv_type == _TAG_UPTIME and tlv_len == 4:
                result["uptime"] = struct.unpack_from(">I", value)[0]
            elif tlv_type == _TAG_HOSTNAME:
                result["hostname"] = value.decode("utf-8", errors="ignore").strip()
            elif tlv_type == _TAG_PLATFORM:
                # Platform string (e.g. "ERLite-3") — use as model if no explicit model yet
                result.setdefault("model", value.decode("utf-8", errors="ignore").strip())
            elif tlv_type == _TAG_ESSID:
                result["essid"] = value.decode("utf-8", errors="ignore").strip()
            elif tlv_type == _TAG_WMODE and tlv_len == 1:
                result["wmode"] = "ap" if value[0] == 3 else "station"
            elif tlv_type == _TAG_WEBUI:
                result["webui"] = value.decode("utf-8", errors="ignore").strip()
            elif tlv_type in (_TAG_MODEL_V1, _TAG_MODEL_V2):
                # Explicit model tag (takes precedence over platform tag)
                result["model"] = value.decode("utf-8", errors="ignore").strip()
            elif tlv_type == _TAG_SSHD_PORT and tlv_len == 4:
                result["ssh_port"] = struct.unpack_from(">I", value)[0]
        except Exception:
            pass

    return result


def _make_ubiquiti_socket() -> socket.socket:
    """
    Create a UDP socket for Ubiquiti discovery.
    Source port MUST be 10001 — AirOS/airMAX devices filter by source port.
    Falls back to any free port if 10001 is already bound.
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

    Target order:
    1. Multicast 233.89.188.1 — Ubiquiti multicast group (AirOS CPE devices use this)
    2. Per-subnet broadcast addresses
    3. Unicast to each known device IP (crosses routed subnets)
    """
    sock = _make_ubiquiti_socket()
    probes = [_UBIQUITI_PROBE_V1, _UBIQUITI_PROBE_V2]

    # Multicast first, then broadcast, then unicast
    targets = (
        [(_UBIQUITI_MULTICAST, _UBIQUITI_PORT)] +
        [(a, _UBIQUITI_PORT) for a in broadcast_addrs] +
        [(ip, _UBIQUITI_PORT) for ip in unicast_ips]
    )

    try:
        for probe in probes:
            for target in targets:
                try:
                    sock.sendto(probe, target)
                except Exception:
                    pass

        probed_ips = {_UBIQUITI_MULTICAST} | set(broadcast_addrs) | set(unicast_ips)

        results: dict[str, dict] = {}
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                data, addr = sock.recvfrom(65507)
                src_ip = addr[0]
                # Discard tiny packets from devices we didn't probe
                # (they're sending their own discovery probes, not responses)
                if src_ip not in probed_ips and len(data) <= 4:
                    continue
                if len(data) < 4 or data[0] not in (0x01, 0x02):
                    continue
                parsed = _parse_ubiquiti_response(data)
                if not parsed:
                    continue
                model = parsed.get("model", "")
                if model:
                    parsed["icon"] = _ubiquiti_icon(model)
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
    Also tries multicast to help diagnose devices that ignore unicast probes.
    Used by the /api/debug/ubiquiti endpoint.
    """
    sock = _make_ubiquiti_socket()
    side_packets = []
    try:
        for probe in [_UBIQUITI_PROBE_V1, _UBIQUITI_PROBE_V2]:
            sock.sendto(probe, (ip, _UBIQUITI_PORT))
            # Also send to multicast in case device responds via that path
            try:
                sock.sendto(probe, (_UBIQUITI_MULTICAST, _UBIQUITI_PORT))
            except Exception:
                pass

        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                data, addr = sock.recvfrom(65507)
                src_ip = addr[0]
                if src_ip != ip:
                    side_packets.append({
                        "src_ip":  src_ip,
                        "raw_hex": data.hex(),
                        "raw_len": len(data),
                    })
                    continue
                parsed = _parse_ubiquiti_response(data)
                model = parsed.get("model", "")
                if model:
                    parsed["icon"] = _ubiquiti_icon(model)
                return {
                    "raw_hex":      data.hex(),
                    "raw_len":      len(data),
                    "header":       data[:4].hex(),
                    "src_ip":       src_ip,
                    "parsed":       parsed,
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

    Three complementary strategies:
    - Multicast to 233.89.188.1 (Ubiquiti group — AirOS CPE devices listen here)
    - Broadcast to each subnet's broadcast address (same L2 only)
    - Unicast to every known device IP (works across routed subnets)

    Returns {ip: {hostname?, model?, firmware?, mac?, uptime?, essid?, icon?}}.
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
