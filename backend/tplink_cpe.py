"""
TP-Link CPE (Pharos OS / OpenWrt) SSH client.
Uses paramiko to SSH into the CPE and run wireless client commands.

Requires SSH to be enabled on the CPE (usually on by default in Pharos OS).
Uses the same admin credentials as the web interface.
"""

import asyncio
import re
from typing import Optional

import paramiko


def _get_stations_ssh(ip: str, user: str, password: str) -> list[dict]:
    """
    SSH into CPE and return list of associated wireless clients.
    Tries multiple commands in order of preference.
    """
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        client.connect(
            ip, port=22,
            username=user, password=password,
            timeout=10,
            allow_agent=False,
            look_for_keys=False,
        )

        # Try commands in order — stop at first one that works
        commands = [
            "iwinfo wlan0 assoclist",
            "iw dev wlan0 station dump",
            "iw wlan1 station dump",          # some CPEs use wlan1
            "cat /proc/net/arp",              # fallback: ARP table
        ]

        for cmd in commands:
            try:
                _, stdout, _ = client.exec_command(cmd, timeout=8)
                output = stdout.read().decode("utf-8", errors="replace").strip()
                if output:
                    stations = _parse_stations(output, cmd)
                    if stations:
                        print(f"[tplink_cpe] {ip} SSH '{cmd}' → {len(stations)} clients", flush=True)
                        return stations
            except Exception:
                continue

    except Exception as e:
        print(f"[tplink_cpe] SSH {ip} error: {type(e).__name__}: {e}", flush=True)
    finally:
        client.close()

    return []


def _parse_stations(output: str, cmd: str) -> list[dict]:
    """Parse MAC addresses from iwinfo/iw/arp output."""
    stations = []
    mac_re = re.compile(r"([0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5})")

    if "assoclist" in cmd:
        # iwinfo wlan0 assoclist:
        # AA:BB:CC:DD:EE:FF  -65 dBm / -95 dBm (SNR 30)  0 ms ago
        for line in output.splitlines():
            line = line.strip()
            m = mac_re.match(line)
            if m:
                entry = {"mac": m.group(1).upper()}
                # Parse signal
                sig = re.search(r"(-\d+)\s*dBm", line)
                if sig:
                    entry["signal"] = int(sig.group(1))
                stations.append(entry)

    elif "station dump" in cmd:
        # iw dev wlan0 station dump:
        # Station AA:BB:CC:DD:EE:FF (on wlan0)
        #   signal: -65 dBm
        current: dict = {}
        for line in output.splitlines():
            m = re.match(r"Station\s+([0-9A-Fa-f:]{17})", line.strip())
            if m:
                if current:
                    stations.append(current)
                current = {"mac": m.group(1).upper()}
            elif current:
                sig = re.search(r"signal:\s*(-\d+)", line)
                if sig:
                    current["signal"] = int(sig.group(1))
        if current:
            stations.append(current)

    else:
        # Generic: extract any MAC addresses
        seen = set()
        for mac in mac_re.findall(output):
            mac = mac.upper()
            if mac not in seen:
                seen.add(mac)
                stations.append({"mac": mac})

    return stations


async def get_stations(ip: str, user: str, password: str) -> list[dict]:
    """Return list of connected wireless clients via SSH."""
    print(f"[tplink_cpe] get_stations SSH {ip}", flush=True)
    return await asyncio.to_thread(_get_stations_ssh, ip, user, password)
