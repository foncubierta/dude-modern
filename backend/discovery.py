"""
Passive network discovery via mDNS, SSDP and NetBIOS.
All three return {ip: name} dicts used to enrich device hostnames.
"""

import asyncio
import re
import socket
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
